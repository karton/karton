NULL=

CHECK_PRG=./scripts/check-program
SVG2PNG=./scripts/svg2png

LOGO_SIZES = \
	16 \
	22 \
	32 \
	48 \
	64 \
	128 \
	256 \
	512 \
	$(NULL)

LOGOS = $(patsubst %,logos/out/karton-%.png,$(LOGO_SIZES))

.PHONY: automatic-target
automatic-target:
	@echo "Nothing to build automatically!" >&2; exit 1

.PHONY: lint
lint:
	./scripts/lint.sh

.PHONY: logos
logos: $(LOGOS)

logos/out/.stamp:
	mkdir -p `dirname $@`
	touch $@

logos/out/karton-16.png: logos/src/karton-16.png logos/out/.stamp
	cp $< $@

logos/out/karton-22.png: logos/src/karton-22.png logos/out/.stamp
	cp $< $@

logos/out/karton-32.png: logos/src/karton-small.svg logos/out/.stamp
	$(SVG2PNG) $< $@ 32

logos/out/karton-48.png: logos/src/karton-small.svg logos/out/.stamp
	$(SVG2PNG) $< $@ 48

logos/out/karton-64.png: logos/src/karton.svg logos/out/.stamp
	$(SVG2PNG) $< $@ 64

logos/out/karton-128.png: logos/src/karton.svg logos/out/.stamp
	$(SVG2PNG) $< $@ 128

logos/out/karton-256.png: logos/src/karton.svg logos/out/.stamp
	$(SVG2PNG) $< $@ 256

logos/out/karton-512.png: logos/src/karton.svg logos/out/.stamp
	$(SVG2PNG) $< $@ 512
