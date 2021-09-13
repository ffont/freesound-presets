# Freesound Presets

This is a utility to create sampler presets from Freesound sound and export them to a variety of sampler device formats.


## How to use
 
 * Clone the repository and `cd` to it

 * Make a copy of `api_key.example.py` and rename it to `apikey.py`. [Generate an API key from Freesoud](https://freesound.org/apiv2/apply) and add it to `apikey.py`.
 
 * Build docker image

```
docker build -t freesound-presets .
```

 * Help command

```
docker run -it --rm -v `pwd`:/app freesound-presets -h
usage: freesound-presets.py [-h] [-v] -t TYPE [-p PACK] [-l] -n NAME [-i] [-c] [-o]

Freesound Presets. Generates sampler presets based on Freesound sounds and exports them in differen sampler formats.

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         if set, prints detailed info on screen
  -e EXPORTER, --exporter EXPORTER
                        one of ['source', 'blackbox']
  -t TYPE, --type TYPE  one of ['instrument', '16pad', 'loops']
  -p PACK, --pack PACK  Freesound pack ID to get instrument samples from
  -q QUERY, --query QUERY
                        Textual query for 16pad presets
  -l, --loop            configure sounds to loop
  -n NAME, --name NAME  name for the output preset
  -i, --include-sounds  include sound files with the preset
  -c, --convert         convert included sound files to WAV
  -o, --originals       use original sound files when downloading

```

 * Run the image and pass arguments to create presets

```
# Create instrument presets for "source"
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21055 -n Piano
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 24590 -n DDRM -l
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 17250 -n 'DSI tetra' -l
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 17272 -n 'Analog Four'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 17166 -n 'Akai AX80 - Moog'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 20236 -n 'Cello'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 22511 -n 'Guitar'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 2653 -n 'NoiseCollector organ'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 5084 -n 'Jovica Layers pad'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 3957 -n 'Fender Rhodes'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21034 -n 'Curch organ'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21035 -n 'Organ quiet'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 12231 -n 'Orchestra bells'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21027 -n 'Glockenspiel'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21030 -n 'Marimba'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21042 -n 'Timpani'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21065 -n 'Xylophone'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21029 -n 'Harp'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21015 -n 'Double Bass Pizzicato'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21017 -n 'Double Bass Solo'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21016 -n 'Double Bass Spicatto'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21038 -n 'Violin'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21001 -n 'Bassoon'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21002 -n 'Bassoon Vibrato'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21013 -n 'Clarinet'
docker run -it --rm -v `pwd`:/app freesound-presets -e source -t instrument -p 21023 -n 'Flute'

# Create 16-pad presets for "blackbox"
docker run -it --rm -v `pwd`:/app freesound-presets -e blackbox -t 16pad -q 'percussion' -n 'FsPerc' -ic
docker run -it --rm -v `pwd`:/app freesound-presets -e blackbox -t 16pad -q 'wood' -n 'FsWood' -ic
docker run -it --rm -v `pwd`:/app freesound-presets -e blackbox -t 16pad -q 'wood' -n 'FsGlass' -ic

# Create loops presets for "blackbox"
docker run -it --rm -v `pwd`:/app freesound-presets -e blackbox -t loops -q '120bpm' -n 'Fs120Bpm' -ic
```
