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
KERBEROS_DIR=$(HERE)/src/kerberos/kerberos/build
ZP_DIR=$(HERE)/ZenPacks/zenoss/Microsoft/Windows
LIB_DIR=$(ZP_DIR)/lib

default: egg

egg:
	#setup.py will call 'make build' before creating the egg
	python setup.py bdist_egg

builddependencies: | src src/txwinrm src/kerberos
	#cd src/txwinrm; git checkout master; git pull
	#cd ../kerberos; git checkout master; git pull
	#cd src/kerberos
	#cd kerberos; python setup.py build
	rm -rf $(LIB_DIR)/txwinrm
	mkdir $(LIB_DIR)/txwinrm
	cp -r $(TXWINRM_DIR)/*.py $(LIB_DIR)/txwinrm/
	mkdir $(LIB_DIR)/txwinrm/request
	cp -r $(TXWINRM_DIR)/request/*.xml $(LIB_DIR)/txwinrm/request/
	cp $(KERBEROS_DIR)/lib.linux-x86_64-2.7/kerberos.so $(LIB_DIR)/
	
clean:
	rm -rf lib build dist *.egg-info $(LIB_DIR)/txwinrm

src:
	mkdir src

src/txwinrm:
	cd src; git clone https://github.com/zenoss/txwinrm.git

src/kerberos:
	cd src; git clone https://github.com/zenoss/kerberos.git