PYTHON3:=/opt/local/bin/python3.14

STUFF:="$(HOME)/Downloads/BBCMicroScShots.zip" "$(HOME)/tmp/analyze_screen_shot_palettes" 

.PHONY:default
default:
	$(PYTHON3) "./analyze_screen_shot_palettes.py" $(STUFF) $(if $(CLEAN),--clean,) $(if $(CLEAN_IMAGES),--clean-images,)

.PHONY:test1
test1:
	$(PYTHON3) "./analyze_screen_shot_palettes.py" $(STUFF) --clean -g Nutcraka
