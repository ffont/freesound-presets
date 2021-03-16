# Freesound Presets

This is a utility to create sampler presets from Freesound sound and export them to a variety of sampler device formats.


## How to use
 
 * Clone the repository and `cd` to it

 * Build docker image

```
docker build -t freesound-presets .
```

 * Run the image and pass arguments to create presets


```
# See help
docker run -it --rm -v `pwd`:/app freesound-presets -h

# Create instrument presets
docker run -it --rm -v `pwd`:/app freesound-presets -t instrument -p 21055 -n Piano
docker run -it --rm -v `pwd`:/app freesound-presets -t instrument -p 24590 -n DDRM -l
docker run -it --rm -v `pwd`:/app freesound-presets -t instrument -p 17250 -n 'DSI tetra' -l
docker run -it --rm -v `pwd`:/app freesound-presets -t instrument -p 17272 -n 'Analog Four'
docker run -it --rm -v `pwd`:/app freesound-presets -t instrument -p 17166 -n 'Akai AX80 - Moog'
docker run -it --rm -v `pwd`:/app freesound-presets -t instrument -p 20236 -n 'Cello'
docker run -it --rm -v `pwd`:/app freesound-presets -t instrument -p 22511 -n 'Guitar'
```
