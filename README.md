# Look Up

An offline stargazing website that tells you what to look at in the sky tonight and nudges you to go outside.

It runs entirely on your own computer. Python works out what is really in the sky, and a small open-weight AI model (Qwen2.5 1.5B, via Ollama) turns that into a short, friendly nudge. No server, no API key, no internet after setup.

Built for the DEV Hacktoberfest Open-Source AI Challenge, Week 1: **Touch Grass**.

<!-- Add a screenshot of the page here -->

## Features

- Tonight's visible planets: direction, best time and altitude, calculated for your location over the whole night, from sunset to sunrise
- A short AI-written nudge in a voice you choose: Calm, Excited or Poetic
- Location picker: Bengaluru by default, a city list, custom coordinates, or browser location
- **"I'm going out"** button: pick 10, 20, 30, 60 or custom minutes, the page dims, and gentle prompts appear every few minutes until a soft chime ends the timer
- A reply to what you saw when you come back
- Works with Wi-Fi off

## Quick start

You need Python 3.9+ and [Ollama](https://ollama.com).

```
git clone https://github.com/skd-33/look-up.git
cd look-up
pip install -r requirements.txt
python setup.py
ollama pull qwen2.5:1.5b
python server.py
```

Open http://127.0.0.1:8000.

`setup.py` downloads `de421.bsp`, a 17 MB NASA JPL planetary ephemeris, once. The model download is the only other thing that needs internet. After that, turn Wi-Fi off and it still works.

Start the server from a terminal with `python server.py`. Ollama must be running in the background (it starts automatically after install).

## How it works

```
Skyfield + de421.bsp  ->  facts (JSON)  ->  Ollama (Qwen2.5 1.5B)  ->  nudge text
                                   \                                      |
                                    +--------->  local web page  <-------+
```

- **Python decides the facts.** [Skyfield](https://rhodesmill.org/skyfield/) calculates positions from the local ephemeris file. Python picks the target object and a mission line.
- **The model only writes the words.** It receives just the target's facts and rewrites them warmly.
- **The output is checked.** If the text names an object that isn't in the data, or leaves out the time, it is thrown away and a plain template sentence is shown instead.

A 1.5B model is good at tone and unreliable with facts, so it is never trusted with facts.

## Configuration

- Model: set `MODEL` near the top of `server.py`. Any model you have pulled in Ollama works.
- Default location: set `LAT` and `LON` near the top of `server.py`, or change it in the page.
- Port: `PORT` in `server.py` (default 8000).

## Project layout

```
setup.py          one-time download of de421.bsp (the only script that uses the network)
astro.py          what is visible tonight, calculated with Skyfield
nudge.py          builds the prompt, calls Ollama, validates the text
server.py         tiny Python web server and API (127.0.0.1 only)
static/index.html the whole front end: HTML, CSS, JS and the SVG night scene
```

## Why open

Open-weight models let it run on a hilltop with no signal, keep your location on your own machine, cost nothing to run, and let you swap the model or change how it talks with a one-line change.

## Limits

- A small local model writes plainer sentences than a large cloud model would.
- Times use your computer's clock and timezone.
- Brightness and positions are for naked-eye planets only.

## Future ideas

- Start the nudge automatically at login
- Bright stars and ISS passes
- More voices and models