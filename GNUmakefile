##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

# NOTE FOR KERBEROS SUPPORT
#
# The kerberos.so file needs to be built on the OS platform it is intended to support
# To build:
# Download kerberos 1.1.1 from pipi
# 	https://pypi.python.org/pypi/kerberos
#
# yum install gcc krb5-devel python-devel -y
# untar kerberos source
# python setup.py build
#
# kerberos.so will be located in the build directory

ZP_DIR=$(PWD)/ZenPacks/zenoss/Microsoft/Windows

PYTHON=python
SRC_DIR=$(PWD)/src
BUILD_DIR=$(PWD)/build
LIB_DIR=$(ZP_DIR)/lib

# Sets TXWINRM=txwinrm-1.0.0 (or whatever the packaged version is)
TXWINRM=$(patsubst $(SRC_DIR)/%.tar.gz,%,$(wildcard $(SRC_DIR)/txwinrm*.tar.gz))


## Direct Targets ############################################################

default: egg


egg: clean
	@rm -f dist/*.egg
	@python setup.py bdist_egg


install: clean egg
	@zenpack --install $(wildcard $(PWD)/dist/*.egg)


develop: clean
	@zenpack --link --install $(PWD)


clean:
	@cd $(LIB_DIR) && rm -Rf *.pth site.* *.egg *.egg-link
	@rm -rf build dist *.egg-info


## setuptools Targets ########################################################

egg-dependencies: clean
	@mkdir -p $(BUILD_DIR)

	@echo "Unpacking $(TXWINRM) into $(BUILD_DIR)/$(TXWINRM)/"
	@cd $(BUILD_DIR) ; gzip -dc ../src/$(TXWINRM).tar.gz | tar -xf -

	@echo "Installing $(TXWINRM) into $(LIB_DIR)/"
	@cd $(BUILD_DIR)/$(TXWINRM) ; \
		PYTHONPATH="$(PYTHONPATH):$(LIB_DIR)" \
		$(PYTHON) setup.py install \
		--install-lib="$(LIB_DIR)" \
		--install-scripts=_scripts


develop-dependencies: clean
	@if [ -d "$(SRC_DIR)/txwinrm" ]; then \
		echo "Using $(SRC_DIR)/txwinrm" ;\
		cd $(SRC_DIR) ; \
		echo "Linking txwinrm into $(LIB_DIR)/" ; \
		cd txwinrm ; \
			PYTHONPATH="$(PYTHONPATH):$(LIB_DIR)" \
			$(PYTHON) setup.py develop \
			--install-dir="$(LIB_DIR)" \
			--script-dir=_scripts ;\
	else \
		echo "Unpacking $(TXWINRM) into $(SRC_DIR)/$(TXWINRM)/" ; \
		cd $(SRC_DIR) ; \
		gzip -dc ../src/$(TXWINRM).tar.gz | tar -xf - ; \
		echo "Linking $(TXWINRM) into $(LIB_DIR)/" ; \
		cd $(TXWINRM) ; \
			PYTHONPATH="$(PYTHONPATH):$(LIB_DIR)" \
			$(PYTHON) setup.py develop \
			--install-dir="$(LIB_DIR)" \
			--script-dir=_scripts ;\
	fi
