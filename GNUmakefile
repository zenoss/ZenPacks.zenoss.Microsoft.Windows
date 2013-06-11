###########################################################################
#
# This program is part of Zenoss Core, an open source monitoring platform.
# Copyright (C) 2013 Zenoss Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 or (at your
# option) any later version as published by the Free Software Foundation.
#
# For complete information please visit: http://www.zenoss.com/oss/
#
###########################################################################

PYTHON=$(shell which python)
HERE=$(PWD)
TXWINRM_DIR=$(HERE)/src/txwinrm/txwinrm
ZP_DIR=$(HERE)/ZenPacks/zenoss/Microsoft/Windows
LIB_DIR=$(ZP_DIR)/lib

default: egg

egg:
	#setup.py will call 'make build' before creating the egg
	python setup.py bdist_egg

# pipe operator means src/txwinrm must exist (as opposed to being more recent)
build: | src src/txwinrm
	cd src/txwinrm; git pull
	rm -rf $(LIB_DIR)/txwinrm
	mkdir $(LIB_DIR)/txwinrm
	cp -r $(TXWINRM_DIR)/*.py $(LIB_DIR)/txwinrm/
	mkdir $(LIB_DIR)/txwinrm/request
	cp -r $(TXWINRM_DIR)/request/*.xml $(LIB_DIR)/txwinrm/request/

clean:
	rm -rf lib build dist *.egg-info $(LIB_DIR)/txwinrm

src:
	mkdir src

src/txwinrm:
	cd src; git clone https://github.com/zenoss/txwinrm.git
