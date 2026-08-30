PYTHON3:=/opt/local/bin/python3.14

STUFF:="$(HOME)/Downloads/BBCMicroScShots.zip" "./output/" 

.PHONY:default
default:
	$(PYTHON3) "./analyze_screen_shot_palettes.py" $(STUFF) $(if $(CLEAN),--clean,) $(if $(CLEAN_IMAGES),--clean-images,) $(if $(DEBUG),--debug,)

.PHONY:test1
test1:
	$(PYTHON3) "./analyze_screen_shot_palettes.py" $(STUFF) --clean -g Nutcraka
