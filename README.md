# Web server that controls a Toika dobby loom

This server is intended to allow you to control your loom from any phone, tablet or other device that has wifi and a web browser.

This server must run on a computer that is connected (via a USB cable) to your loom.
This code has only been tested on macOS but should also work on any flavor of linux.

Warning: this software ignores the reverse button on the loom;
to change directions you must push the direction arrow on the web display.
This means you should probably run your web browser on a phone or tablet mounted somewhere very convenient,
such as to the front of the castle.
I made this difficult choice because the loom does not report the state of the "reverse" button on the dobby head;
the software has no idea the direction has changed until you request the next pick.
If the direction were set by the "reverse" button, the display would be misleading some of the time.
By controlling direction in softare, the display is always correct.

Warning: this software has not yet been tested on a real loom, because I don't own a Toika loom yet.
Please test it with a computer you already own before buying a dedicated server computer.

## Installing and Running the Web Server

* Decide which computer you will use to run the server.
  A macOS compute will work.
  A Raspberry Pi (probably a model 4 or better) is very likely to work; it is the computer I had in mind when I wrote this software.
  A Windows computer will probably work.

* Install [Python](https://www.python.org/downloads/) 3.11 or later on the computer.

* Install this [toika_loom_server](https://pypi.org/project/toika-loom-server/) package on the computer with command: **pip install toika_loom_server**

* Determine the name of the port that your computer is using to connect to the loom.
  On macOS or linux:

    * Run the command **ls /dev/tty.usb\*** to see which USB ports already in use, if any.

    * Connect your computer to the loom with a USB cable.

    * Turn on the loom and wait a few seconds to let it connect.

    * Run the command **ls /dev/tty.usb\*** again. There should be one new entry,
      which is the name of the port connected to the loom.
  
* If you are using a Raspberry Pi, I strongly recommend [setting a permanent host name](https://www.tomshardware.com/how-to/static-ip-raspberry-pi), so you can always connect your web browser to the same address.
  This step is not necessary for macOS, because it always has a permanent host name.

* If you don't know the host name of your computer, you can query it with command: **hostname**

* Run the web server with command: **run_toika_loom** ***port_name***

    * Special port name **mock** will run a simulated loom (no USB connection required).
      This can give you a chance to try out the user interface.
    
    * If you want to clear out old patterns, you can add the **--reset-db argument**
      or select "Clear Recents" in the pattern menu in the web interface (see below).
  
* You may stop the web server by typing ctrl-C (probably twice).

## Running the Loom

Using any modern web browser, connect to the loom server at address **http://***hostname***:8000** where ***hostname*** is the host name you determined above.
In the resulting window:

* Upload one or more weaving pattern files (standard .wif or FiberWorks .dtx files).
  You can push the "Upload" button or drop the files anywhere onto the web page
  (please make sure the page is gray before you drop the files).

* Select the desired pattern using the "Pattern" drop-down menu.
  The menu shows the 25 most recent patterns you have used.
  You may switch patterns at any time, and the server remembers where you were weaving in each of them.
  This allows you to load several treadlings for one threading (each as a separate pattern file) and switch between them at will.

* To clear out the pattern menu (which may become cluttered over time),
  select "Clear Recents", the last item in the menu.
  This clears out information for all patterns except the current pattern.
  If you want to get rid of the current pattern as well, first load a new pattern (which will not be purged),
  or restart the server with the **--reset-db** command-line argument, as explained above.

You are now ready to weave.

* The pattern display shows woven fabric below and potential future fabric above.
  (This is the opposite of the usual US drawdown).

* There are two rectangles to the right of the pattern display:

    * The short upper rectangle shows the color of the current pick (blank if pick 0),
      or, if you have specified a pick to jump to, then it is the color of that pick.
  
    * The square button below that shows the weave direction: whether you are weaving (green down arrow) or unweaving (red up arrow).
      The arrow points in the direction cloth is moving through the loom.
      You can only change the weave direction by pressing this button;
      the software ignores the "reverse" button on the dobby head
      (for reasons explained near the beginning of this document).

* The software will automatically repeat patterns if you weave or unweave beyond the end.
  However, you must advance twice when you reach an end, before the next set of shafts is raised.
  The first advance will lower all shafts, as a signal that you have finished weaving or unweaving one pattern repeat.
  The next advance will show the desired shed.

* To jump to a different pick and/or repeat number is a two-step process:
  first you request the jump, then you advance to it by pressing the loom's pedal.
  (Two steps are necessary because the loom will not accept an unsolicited command to raise shafts.)
  In detail:

    * Enter the desired pick and/or repeat numbers in the boxes on the "Jump to pick" line.
      The box(es) will turn pink and the Jump button will be enabled.

    * Press the "return" keyboard key or click the "Jump" button on the web page
      to send the requested jump to the server.
      You will see several changes:

      * The jump input boxes will have a white background and the jump button will be disabled.

      * The pattern display will show the new pick in the center row, with a dotted box around it.
        (But if you are only changing the repeat number, the box will be solid.)

    * Advance to the next pick by pressing the loom's pedal.
      Until you advance to the next pick, you can request a different jump
      (in case you got it wrong the first time) or cancel the jump in several ways:
    
      * Press the "Reset" button to the right of "Jump".

      * Reload the page.

      * Select a new pattern.

*  Subtleties:

    * The server only allows one web browser to connect, and the most recent connection attempt wins.
      This prevents a mystery connection from hogging the loom.
      If the connection is dropped on the device you want to use for weaving,
      simply reload the page to regain the connection.

    * Every time you connected to the web server or reload the page, the server refreshes
      its connection to the loom (by disconnecting and immediately reconnecting).
      So if the server is reporting a problem with its connection to the loom,
      and it is not due to the loom losing power, or a disconnected or bad USB cable,
      you might try reloading the page.
    
    * If the loom seems confused, try turning off the loom, waiting a few seconds, then turning it on again.
      Then reload the web page, to force the web server to make a new connection to the loom.

## Remembering Patterns

The web server keeps track of the most recent 25 patterns you have used in a database
(including the most recent pick number and number of repeats, which are restored when you select a pattern).
The patterns in the database are displayed in the pattern menu.
If you shut down the server or there is a power failure, all this information should be retained.

You can reset the database by starting the server with the **--reset-db** argument, as explained above.
You must reset the database if you upgrade the toika_loom_server package and the new database format is incompatible
(in which case the server will fail at startup).
You may also want to reset the database if you are weaving a new project and don't want to see any of the saved patterns.

## Developer Tips

* Consider creating your own virtual environment using venv
  (or conda if you are using anaconda python).
  See instructions on line.

* Most of the work is done in base package [base_loom_server](https://github.com/r-owen/base_loom_server.git),
  so unless you are sure you only want to work on just the `toika_loom_server` package,
  your first step is to install `base_loom_server` as per the Developer Tips section of its readme.

* Now install `toika_loom_server`. The process is almost identical to installing [base_loom_server](https://github.com/r-owen/base_loom_server.git):

  * Download `toika_loom_server` source code from [github](https://github.com/r-owen/toika_loom_server.git).

  * Inside that directory issue the following commands:

    * **pip install -e .** (note the final period) to make an editable installation.
      Or install with **pip install -e .'[dev]'** if you did not install dev tools
      when you installed `base_loom_server` (and it is always safe to use).

    * **pre-commit install** to activate the pre-commit hooks.
    
    * **pytest** to test your installation.

* You may run a mock loom by starting the server with: **run_toika_loom mock**.
  The mock loom does not use a serial port.
  **run_toika_loom** also accepts these command-line arguments:

    * **--reset-db** Reset the pattern database. Try this if you think the database is corrupted.

    * **--verbose** Print more diagnostic information.

* In mock mode the web page shows a few extra controls for debugging.

* Warning: the web server's automatic reload feature, which reloads Python code whenever you save changes, *does not work* with this software.
  Instead you have to kill the web server by typing control-C several times, until you get a terminal prompt, then run the server again.
  This may be a bug in uvicorn; see [this discussion](https://github.com/encode/uvicorn/discussions/2075) for more information.
