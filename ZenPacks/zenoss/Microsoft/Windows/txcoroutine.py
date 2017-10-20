################################################################################
# Copyright (c) 2012, Erik Allik
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
################################################################################

from __future__ import print_function

import types
import warnings
from sys import exc_info

from twisted.internet.defer import Deferred, _DefGen_Return, CancelledError
from twisted.python import failure
from twisted.python.util import mergeFunctionMetadata


def _inlineCallbacks(result, g, deferred):
    """
    See L{inlineCallbacks}.
    """
    # This function is complicated by the need to prevent unbounded recursion
    # arising from repeatedly yielding immediately ready deferreds.  This while
    # loop and the waiting variable solve that by manually unfolding the
    # recursion.

    waiting = [True,  # waiting for result?
               None]  # result

    while 1:
        try:
            # Send the last result back as the result of the yield expression.
            isFailure = isinstance(result, failure.Failure)
            if isFailure:
                if deferred.cancelling:  # must be that CancelledError that we want to ignore
                    return
                result = result.throwExceptionIntoGenerator(g)
            else:
                result = g.send(result)
        except _NoReturn as e:
            if isinstance(e._gen, Deferred):
                e._gen.chainDeferred(deferred)
                break
            elif isinstance(e._gen, types.GeneratorType):
                g = e._gen
                result = None
                continue
            else:
                retval = e._gen
                deferred.callback(retval)
                return deferred
        except StopIteration:
            # fell off the end, or "return" statement
            deferred.callback(None)
            return deferred
        except _DefGen_Return, e:
            # returnValue() was called; time to give a result to the original
            # Deferred.  First though, let's try to identify the potentially
            # confusing situation which results when returnValue() is
            # accidentally invoked from a different function, one that wasn't
            # decorated with @inlineCallbacks.

            # The traceback starts in this frame (the one for
            # _inlineCallbacks); the next one down should be the application
            # code.
            appCodeTrace = exc_info()[2].tb_next
            if isFailure:
                # If we invoked this generator frame by throwing an exception
                # into it, then throwExceptionIntoGenerator will consume an
                # additional stack frame itself, so we need to skip that too.
                appCodeTrace = appCodeTrace.tb_next
            # Now that we've identified the frame being exited by the
            # exception, let's figure out if returnValue was called from it
            # directly.  returnValue itself consumes a stack frame, so the
            # application code will have a tb_next, but it will *not* have a
            # second tb_next.
            if appCodeTrace.tb_next.tb_next and appCodeTrace.tb_next.tb_next.tb_next:
                # If returnValue was invoked non-local to the frame which it is
                # exiting, identify the frame that ultimately invoked
                # returnValue so that we can warn the user, as this behavior is
                # confusing.
                ultimateTrace = appCodeTrace
                while ultimateTrace.tb_next.tb_next:
                    ultimateTrace = ultimateTrace.tb_next
                filename = ultimateTrace.tb_frame.f_code.co_filename
                lineno = ultimateTrace.tb_lineno
                warnings.warn_explicit(
                    "returnValue() in %r causing %r to exit: "
                    "returnValue should only be invoked by functions decorated "
                    "with inlineCallbacks" % (
                        ultimateTrace.tb_frame.f_code.co_name,
                        appCodeTrace.tb_frame.f_code.co_name),
                    DeprecationWarning, filename, lineno)
            deferred.callback(e.value)
            return deferred
        except:
            deferred.errback()
            return deferred

        if isinstance(result, Deferred):
            deferred.depends_on = result

            # a deferred was yielded, get the result.
            def gotResult(r):
                if waiting[0]:
                    waiting[0] = False
                    waiting[1] = r
                else:
                    _inlineCallbacks(r, g, deferred)

            result.addBoth(gotResult)
            if waiting[0]:
                # Haven't called back yet, set flag so that we get reinvoked
                # and return from the loop
                waiting[0] = False
                return deferred

            result = waiting[1]
            # Reset waiting to initial values for next loop.  gotResult uses
            # waiting, but this isn't a problem because gotResult is only
            # executed once, and if it hasn't been executed yet, the return
            # branch above would have been taken.

            waiting[0] = True
            waiting[1] = None

    return deferred


def coroutine(f):  # originally inlineCallbacks
    """Enhanced version of twisted.internet.defer.inlineCallbacks with fuller support coroutine functionality.

    Please see the documentation for twisted.internet.defer.inlineCallbacks for more information.

    See also: txcoroutine.noreturn for information on how to use optimized tail recursion with this decorator.

    """
    def unwindGenerator(*args, **kwargs):
        try:
            gen = f(*args, **kwargs)
        except (_DefGen_Return, _NoReturn) as e:
            badUsage = 'returnValue' if isinstance(e, _DefGen_Return) else 'noreturn'
            raise TypeError(
                "inlineCallbacks requires %r to produce a generator; instead "
                "caught %s being used in a non-generator" % (f, badUsage,))
        if not isinstance(gen, types.GeneratorType):
            raise TypeError(
                "inlineCallbacks requires %r to produce a generator; "
                "instead got %r" % (f, gen))

        return _inlineCallbacks(None, gen, Coroutine(canceller=lambda _: gen.close()))

    return mergeFunctionMetadata(f, unwindGenerator)


_swallow_cancelled_error = lambda f: f.trap(CancelledError)


class Coroutine(Deferred):
    # this is something like chaining, but firing of the other deferred does not cause this deferred to fire.
    # also, we manually unchain and rechain as the coroutine yields new Deferreds.
    cancelling = False
    depends_on = None

    def pause(self):
        if self.depends_on:
            self.depends_on.pause()
        return Deferred.pause(self)

    def unpause(self):
        if self.depends_on:
            self.depends_on.unpause()
        return Deferred.unpause(self)

    def cancel(self):
        # to signal _inlineCallbacks to not fire self.errback with CancelledError;
        # otherwise we'd have to call `Deferred.cancel(self)` immediately, but it
        # would be semantically unnice if, by the time the coroutine is told to do
        # its clean-up routine, the inner Deferred hadn't yet actually been cancelled.
        self.cancelling = True

        # the _swallow_cancelled_error errback is added as the last one, so anybody else who is already listening for
        # CancelledError will still get it.

        if self.depends_on:
            self.depends_on.addErrback(_swallow_cancelled_error)
            self.depends_on.cancel()
            del self.depends_on

        self.addErrback(_swallow_cancelled_error)
        Deferred.cancel(self)


class _NoReturn(BaseException):
    """Uused internally in the cooperation between noreturn and the customized inlineCallbacks in util._defer."""
    def __init__(self, gen):
        self._gen = gen


def noreturn(gen):
    """Marks a function call that does not return to the current caller.

    Can only be used within generators wrapped with `@inlineCallbacks`. Supports calling of regular functions, and
    functions that either return a generator or a Deferred.

    When used with a function `foo` that returns a `Deferred`, it is functionally equivalent to but more memory
    efficient than `returnValue((yield foo()))`.

    """
    raise _NoReturn(gen)
