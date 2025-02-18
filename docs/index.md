# Toika Web Server

Software that allows you to control a Toika dobby loom
from any modern web browser, e.g. on a phone or tablet.

The main [documentation](https://r-owen.github.io/base_loom_server/)
explains how to install and use this software.

Please also read the following Toika-specific information:

## Toika-Specific Information

When running the Toika loom server, have must decide how you want to change weaving direction
(weaving or unweaving). You have two choices,

* Software controls the weave direction.
  To change direction, press the square button that shows the weave direction
  (a green or red arrow) on the web display.
  The physical button on the dobby head is **ignored**.

* The loom controls the weave direction. You have to press the physical button
  on the dobby head to change direction. The square button showing weave direction
  is only a display (you can't click it).

If your web display device (i.e. phone or tablet) is mounted where you can easily reach it,
then I recommend software control of direction, because the direction display will always be correct.

If your web display device is *not* in a convenient location, then have the loom control direction.
Unfortunately, in this mode the displayed direction will sometimes be wrong.
This is because the loom does not report anything when you press the direction button.
The software can't see that anything has changed until the next time the loom asks for a pick
(i.e. when you press the pedal).

To have the loom control weaving direction, start the loom server with extra command-line argument `--weave-direction loom`. To have software control weaving direction, omit this, or specify `--weave-direction software`.

## The Software

toka_loom_sever is served at [PyPI](https://pypi.org/project/toika-loom-server/). That page has links to the source repository, issue tracker, and back to this documentation.
