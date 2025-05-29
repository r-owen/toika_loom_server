# Toika Web Server

Software that allows you to control a Toika dobby loom
from any modern web browser, e.g. on a phone or tablet.

For more information, read the main [documentation](https://r-owen.github.io/base_loom_server/), plus the Toika-Specific information below.

## Toika-Specific Information

When running the Toika loom server, you must decide how you want to change weaving direction
(between weaving and unweaving). You have two choices:

* Software controls the weave direction.
  To change direction, press the square button on the web display that shows the weave direction
  (a green or red arrow).
  The REVERSE button on the dobby head is **ignored**.

* The dobby head controls the weave direction.
  To change direction, toggle the REVERSE button on the dobby head.
  The software displays the direction of the *previous* pick.

If your web display device (i.e. phone or tablet) is mounted where you can easily reach it,
then I recommend software control of direction, because the direction display will always be correct.

If your web display device is *not* in a convenient location, then have the loom control direction.
Unfortunately, in this mode the displayed direction will sometimes be wrong.
This is because the loom does not report anything when you toggle the REVERSE button.
The software can't see that anything has changed until you request the next pick.

To have the loom control weaving direction, start the loom server with extra command-line argument `--direction-control loom`. To have software control weaving direction, omit this, or specify `--direction-control software`.

## The Software

toka_loom_sever is served at [PyPI](https://pypi.org/project/toika-loom-server/). That page has links to the source repository, issue tracker, and back to this documentation.

## Acknowledgements

Thanks to Jukka Yrjölä and Jarkko Yrjölä from Toika for providing the API and helpful clarification.

Thanks to WillowGoose ([willowlovestoweave](https://www.instagram.com/willowlovestoweave/) on Instagram) for patiently testing this software and proving valuable feedback.
