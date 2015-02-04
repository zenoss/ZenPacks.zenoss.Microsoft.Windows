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
#
# yum install gcc krb5-devel python-devel -y
# cd src/pykerberos
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
	@rm -Rf $(LIB_DIR)/txwinrm
	@rm -rf build dist *.egg-info

test:
	runtests ZenPacks.zenoss.Microsoft.Windows

analytics:
	rm -f ZenPacks/zenoss/Microsoft/Windows/analytics/analytics-bundle.zip
	mkdir -p analytics/resources/public/Microsoft_Windows_ZenPack
	./create-analytics-bundle \
		--folder="Microsoft Windows ZenPack" \
		--domain="Microsoft Windows Domain" \
		--device=10.175.211.133
	cd analytics; zip -r ../ZenPacks/zenoss/Microsoft/Windows/analytics/analytics-bundle.zip *


## setuptools Targets ########################################################

egg-dependencies: clean
	@mkdir -p $(BUILD_DIR)

	@echo "Unpacking $(TXWINRM) into $(BUILD_DIR)/$(TXWINRM)/"
	@cd $(BUILD_DIR) ; gzip -dc ../src/$(TXWINRM).tar.gz | tar -xf -

	@echo "Building $(TXWINRM)"
	@cd $(BUILD_DIR)/$(TXWINRM) ; $(PYTHON) setup.py build >/dev/null

	@echo "Copying $(TXWINRM) into $(LIB_DIR)/"
	@mkdir -p $(LIB_DIR)/txwinrm
	@cd $(BUILD_DIR)/$(TXWINRM)/txwinrm ; \
		tar -c --exclude test . | tar -x -C $(LIB_DIR)/txwinrm

develop-dependencies: clean
	@if [ -d "$(SRC_DIR)/txwinrm" ]; then \
		echo "Linking $(SRC_DIR)/txwinrm/txwinrm into $(LIB_DIR)/" ; \
		ln -sf $(SRC_DIR)/txwinrm/txwinrm $(LIB_DIR)/ ; \
	else \
		echo "Unpacking $(TXWINRM) into $(SRC_DIR)/$(TXWINRM)/" ; \
		cd $(SRC_DIR) ; gzip -dc ../src/$(TXWINRM).tar.gz | tar -xf - ; \
		echo "Linking $(SRC_DIR)/$(TXWINRM)/txwinrm into $(LIB_DIR)/" ; \
		ln -sf $(SRC_DIR)/$(TXWINRM)/txwinrm $(LIB_DIR)/ ; \
	fi
