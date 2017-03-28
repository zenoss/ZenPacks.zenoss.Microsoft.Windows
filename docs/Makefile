OUTPUT_HTML = windows.html

docs:
	pandoc header.md --template=template.html > $(OUTPUT_HTML)
	pandoc releases.md --template=template.html >> $(OUTPUT_HTML)
	pandoc body.md --template=template.html --table-of-contents >> $(OUTPUT_HTML)
