import ffmpeg
import logging
import threading
import os
import urllib
import shutil
import errno

logger = logging.getLogger()


def convert_to_wav(input_filename, output_filename, samplerate=44100):
    if not os.path.exists(output_filename):
        ffmpeg.input(input_filename).output(output_filename, ac=2).run(quiet=True, overwrite_output=True)


class SoundDownloaderProgress:

    def __init__(self, url):
        self.url = url

    def download_progress_hook(self, count, blockSize, totalSize):
        percent = int(count * blockSize * 100 / totalSize)
        logger.debug('    - Downloading {}: {}%'.format(self.url, percent))


def download_sound(url, outfile, access_token=None):
    if not (os.path.exists(outfile) and os.path.getsize(outfile) > 0):
        progress = SoundDownloaderProgress(url)
        if access_token is not None:
            # Download original quality file, set the auth header
            opener = urllib.request.build_opener()
            opener.addheaders = [('Authorization', 'Bearer {}'.format(access_token))]
            urllib.request.install_opener(opener)
        
        try:
            urllib.request.urlretrieve(url, outfile, reporthook=progress.download_progress_hook)
        except urllib.error.ContentTooShortError as e:
            print(e)


class DownloadAndConvertSoundsThread(threading.Thread):

    def __init__(self, url, sound_id, sound_type=None, access_token=None, convert=True):
        super(DownloadAndConvertSoundsThread, self).__init__()
        self.url = url
        self.sound_id = sound_id
        self.access_token = access_token
        self.sound_type = sound_type
        
        if sound_type is None:
            sound_type = url.split('.')[-1]
        self.outfile_download = os.path.join('/tmp', '{}.{}'.format(sound_id, sound_type))

        if not os.path.exists('/app/audio'):
            os.mkdir('/app/audio')

        self.convert = convert
        if convert:
            self.outfile = '/app/audio/{}.wav'.format(sound_id)
        else:
            self.outfile = '/app/audio/{}.{}'.format(sound_id, sound_type)

    def run(self):
        if not (os.path.exists(self.outfile) and os.path.getsize(self.outfile) > 0):
            download_sound(self.url, self.outfile_download, access_token=self.access_token)
            if self.convert:
                convert_to_wav(self.outfile_download, self.outfile)
            else:
                shutil.copy(self.outfile_download, self.outfile)


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


class SourceExporter(object):

    device_name = 'Source'

    def __init__(self, sounds, preset_number=0, preset_name="NoName", loop=0, include_sounds=False):
        self.sounds = sounds
        self.preset_name = preset_name
        self.preset_number = preset_number
        self.loop = loop
        self.include_sounds = include_sounds

    def get_base_path(self):
        return os.path.join('/app/presets', self.device_name)
   
    def get_preset_file_path(self):
        return os.path.join(self.get_base_path(), '{}.xml'.format(self.preset_name))

    def get_sound_file_path(self):
        return os.path.join(self.get_base_path(), 'sounds')

    def save_preset_file(self, file_contents):
        file_path = self.get_preset_file_path()
        mkdir_p(os.path.dirname(file_path))
        fid = open(file_path, 'w')
        fid.write(file_contents)
        fid.close()

    def save_sound_file(self, sound):
        file_path = os.path.join(self.get_base_path(), 'sounds', sound['path'].split('/')[-1])
        if not os.path.exists(file_path):
            mkdir_p(os.path.dirname(file_path))
            try:
                shutil.copy(sound['path'], file_path)
            except:
                pass

    def export(self):
        if len(self.sounds) == 0:
            logger.info('- No sounds to export...')
            return

        logger.info('- Exporting preset of {} sounds with {} exporter'.format(len(self.sounds), self.device_name))
        sounds_info = ""
        for count, sound in enumerate(self.sounds):

            assinged_notes_aux = ['0'] * 128
            for note in sound['midi_notes']:
                assinged_notes_aux[note] = '1'
            midi_notes_hex = hex(int("".join(reversed(''.join(assinged_notes_aux))), 2)) 

            sound.update({
                'count': count,
                'midi_notes_hex': midi_notes_hex,
                'launchMode': 1 if self.loop else 0
            })
            sounds_info += '''    
    <soundInfo soundId="{id}" soundName="{name}" soundUser="{username}" soundLicense="{license}" soundOGGURL="{preview_url}" downloadProgress="100" soundDurationInSeconds="{duration}">
        <fsAnalysis/>
        <SamplerSound midiNotes="{midi_notes_hex}" loadedPreviewVersion="1" soundIdx="{count}">
        <SamplerSoundParameter parameter_type="int" parameter_name="launchMode" parameter_value="{launchMode}"/>
        <SamplerSoundParameter parameter_type="float" parameter_name="startPosition" parameter_value="{start_percentage}"/>
        <SamplerSoundParameter parameter_type="float" parameter_name="loopStartPosition" parameter_value="0.3"/>
        <SamplerSoundParameter parameter_type="float" parameter_name="loopEndPosition" parameter_value="0.5"/>
        <SamplerSoundParameter parameter_type="float" parameter_name="gain" parameter_value="-10.0"/>
        <SamplerSoundParameter parameter_type="int" parameter_name="midiRootNote" parameter_value="{midi_note}"/>
        <SamplerSoundParameter parameter_type="float" parameter_name="vel2CutoffAmt" parameter_value="12.0"/>
        <SamplerSoundParameter parameter_type="float" parameter_name="vel2GainAmt" parameter_value="0.75"/>
        </SamplerSound>
    </soundInfo>'''.format(**sound)

        contents = '''<?xml version="1.0" encoding="UTF-8"?>

<SourcePresetState presetName="{0}" presetNumber="{1}" noteLayoutType="0">
  <Sampler NumVoices="16">
    <ReverbParameters reverb_roomSize="0.0" reverb_damping="0.0" reverb_wetLevel="0.0"
                      reverb_dryLevel="1.0" reverb_width="1.0" reverb_freezeMode="1.0"/>
  </Sampler>
  <soundsInfo>
    {2}
  </soundsInfo>
</SourcePresetState>'''.format(
            self.preset_name,
            self.preset_number,
            sounds_info
        )

        self.save_preset_file(contents)
        if self.include_sounds:
            for sound in self.sounds:
                self.save_sound_file(sound)
