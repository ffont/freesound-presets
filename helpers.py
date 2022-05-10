import ffmpeg
import logging
import threading
import os
import urllib
import shutil
import errno
import uuid

logger = logging.getLogger()

def generate_uuid():
    return uuid.uuid4().hex


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


class BaseExporter(object):

    device_name = 'Base'
    extension = 'ext'
    supported_types = []

    def __init__(self, sounds, sound_overwrite_exporter_fields=None, ptype=None, preset_number=0, preset_name="NoName", include_sounds=False):
        self.sounds = sounds
        self.sound_overwrite_exporter_fields = sound_overwrite_exporter_fields
        self.preset_name = preset_name
        self.preset_number = preset_number
        self.include_sounds = include_sounds

        if sound_overwrite_exporter_fields is not None:
            assert (len(sounds) == len(sound_overwrite_exporter_fields)), 'Number of sounds and number of overwrite fields for sounds does not match'

        assert (ptype in self.supported_types), 'Unsupported preset type for exporter'

    def get_base_path(self):
        return os.path.join('/app/presets', self.device_name)
   
    def get_preset_file_path(self):
        return os.path.join(self.get_base_path(), '{}.{}'.format(self.preset_name, self.extension))

    def get_sound_file_base_path(self):
        return os.path.join(self.get_base_path(), 'sounds')

    def get_sound_file_path(self, sound):
        return os.path.join(self.get_sound_file_base_path(), sound['path'].split('/')[-1])

    def get_converted_sound_file_path(self, sound):
        return os.path.join(self.get_sound_file_base_path(), sound['path'].split('/')[-1].split('.')[0] + '.wav')

    def save_preset_file(self, file_contents):
        file_path = self.get_preset_file_path()
        mkdir_p(os.path.dirname(file_path))
        fid = open(file_path, 'w')
        fid.write(file_contents)
        fid.close()

    def save_sound_file(self, sound, convert_to_wav=False):
        file_path = self.get_sound_file_path(sound)
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
        file_contents = self.get_file_contents_for_device()
        
        self.save_preset_file(file_contents)
        if self.include_sounds:
            for sound in self.sounds:
                self.save_sound_file(sound)

    def get_file_contents_for_device(self):
        raise NotImplementedError

        
class SourceExporter(BaseExporter):

    device_name = 'Source'
    extension = 'xml'
    supported_types = ['instrument']

    def get_file_contents_for_device(self):
        midi_velocities = [] 
        for count, sound in enumerate(self.sounds):
            midi_velocities.append(sound.get('midi_velocity', 0))
        midi_velocities = sorted(list(set(midi_velocities)))
        midi_layers_map = {midi_velocity: layer_n for layer_n, midi_velocity in enumerate(midi_velocities)}
        midi_layers_map[0] = 0
        for count, sound in enumerate(self.sounds):
            sound.update({
                'uuid': generate_uuid(),
                'velocity_layer': midi_layers_map[sound.get('midi_velocity', 0)]
            })
            if self.sound_overwrite_exporter_fields is not None:
                sound.update(self.sound_overwrite_exporter_fields[count])
        assinged_notes_aux = ['1'] * 128
        all_midi_notes_hex = str(hex(int("".join(reversed(''.join(assinged_notes_aux))), 2)))[2:]
        sounds_info = '''
  <SOUND uuid="{uuid}" launchMode="{launchMode}" startPosition="{start_percentage}"
         loopStartPosition="0.3" loopEndPosition="0.5" gain="-10.0" vel2CutoffAmt="12.0"
         vel2GainAmt="0.75" midiChannel="0" midiNotes="{midi_notes_hex}">'''.format(**{
                'uuid': generate_uuid(),
                'start_percentage': self.sounds[0]['start_percentage'],
                'midi_notes_hex': all_midi_notes_hex,
                'launchMode': self.sounds[0]['launchMode']
            })
        for count, sound in enumerate(self.sounds):
            sounds_info += '''    
    <SOUND_SAMPLE uuid="{uuid}" name="{name}" 
                  soundId="{id}" format="{type}" duration="{duration}" soundFromFreesound="1" filesize="{filesize}"
                  previewURL="{preview_url}" 
                  usesPreview="0" midiRootNote="{midi_note}" midiVelocityLayer="{velocity_layer}" username="{username}"
                  license="{license}">
    </SOUND_SAMPLE>'''.format(**sound)
        sounds_info += '''
  </SOUND>'''

        contents = '''<?xml version="1.0" encoding="UTF-8"?>

<PRESET uuid="{0}" name="{1}" noteLayoutType="0" numVoices="8" reverbDamping="0.0" 
        reverbWetLevel="0.0" reverbDryLevel="1.0" reverbWidth="0.5" reverbFreezeMode="0.0" 
        reverbRoomSize="0.5">{2}
</PRESET>'''.format(
            generate_uuid(),
            self.preset_name,
            sounds_info
        )

        return contents


class BlackboxExporter(BaseExporter):

    device_name = 'Blackbox'
    extension = 'xml'
    supported_types = ['16pad', 'loops']

    def get_base_path(self):
        return os.path.join('/app/presets', self.device_name, self.preset_name)

    def get_sound_file_base_path(self):
        return self.get_base_path()

    def get_preset_file_path(self):
        return os.path.join(self.get_base_path(), 'preset.xml')

    def get_file_contents_for_device(self):

        sounds_info = ""
        sounds = self.sounds[:16]
        if len(self.sounds) < 16:
            for i in range(0, 16 - self.sounds):
                sounds.append(None)

        for count, sound in enumerate(sounds):
            if sound is not None:
                sound.update({
                    'row': count % 4,
                    'column': count // 4,
                    'filename': '.\\' + self.get_converted_sound_file_path(sound).split('/')[-1],
                    'sample_length': int(sound['duration'] * 44100),
                    'stype': 'sample',
                    'samtrigtype': 0,
                    'loopmode': 0,
                    'cellmode': 0,
                })
                if self.sound_overwrite_exporter_fields is not None:
                    sound.update(self.sound_overwrite_exporter_fields[count])
                sounds_info += '''
        <cell row="{row}" column="{column}" layer="0" filename="{filename}" type="{stype}">
            <params gaindb="0" pitch="0" panpos="0" samtrigtype="{samtrigtype}" loopmode="{loopmode}" loopmodes="0" midimode="0" midioutchan="0" reverse="0" cellmode="{cellmode}" envattack="0" envdecay="0" envsus="1000" envrel="200" samstart="0" samlen="{sample_length}" loopstart="0" loopend="{sample_length}" quantsize="3" synctype="5" actslice="1" outputbus="0" polymode="0" slicestepmode="0" chokegrp="0" dualfilcutoff="0" rootnote="0" beatcount="0" fx1send="0" fx2send="0" multisammode="0" interpqual="0" playthru="0" slicerquantsize="13" slicersync="0" padnote="0" loopfadeamt="0" grainsize="0" graincount="3" gainspreadten="0" grainreadspeed="1000" recpresetlen="0" recquant="3" recinput="0" recusethres="0" recthresh="-20000" recmonoutbus="0"/>
            <modsource dest="gaindb" src="velocity" slot="0" amount="400"/>
            <slices/>
        </cell>'''.format(**sound)

            else:
                sounds_info += '''
        <cell row="{row}" column="{column}" layer="0" filename="" type="samtempl">
            <params gaindb="0" pitch="0" panpos="0" samtrigtype="0" loopmode="0" loopmodes="0" midimode="0" midioutchan="0" reverse="0" cellmode="0" envattack="0" envdecay="0" envsus="1000" envrel="200" quantsize="3" synctype="5" outputbus="0" polymode="0" slicestepmode="0" chokegrp="0" dualfilcutoff="0" rootnote="0" beatcount="0" fx1send="0" fx2send="0" interpqual="0" playthru="0" padnote="0" deftemplate="1" recpresetlen="0" recquant="3" recinput="0" recusethres="0" recthresh="-20000" recmonoutbus="0"/>
            <slices/>
        </cell>'''.format(**sound)

        contents = '''<?xml version="1.0" encoding="UTF-8"?>

<document>
    <session>{}
        <cell row="0" column="4" layer="0" filename="" type="samtempl">
            <params gaindb="0" pitch="0" panpos="0" samtrigtype="0" loopmode="0" loopmodes="0" midimode="0" midioutchan="0" reverse="0" cellmode="0" envattack="0" envdecay="0" envsus="1000" envrel="200" quantsize="3" synctype="5" outputbus="0" polymode="0" slicestepmode="0" chokegrp="0" dualfilcutoff="0" rootnote="0" beatcount="0" fx1send="0" fx2send="0" interpqual="0" playthru="0" padnote="0" deftemplate="1" recpresetlen="0" recquant="3" recinput="0" recusethres="0" recthresh="-20000" recmonoutbus="0"/>
            <slices/>
        </cell>
        <cell row="1" column="4" layer="0" filename="" type="samtempl">
            <params gaindb="0" pitch="0" panpos="0" samtrigtype="0" loopmode="0" loopmodes="0" midimode="0" midioutchan="0" reverse="0" cellmode="0" envattack="0" envdecay="0" envsus="1000" envrel="200" quantsize="3" synctype="5" outputbus="0" polymode="0" slicestepmode="0" chokegrp="0" dualfilcutoff="0" rootnote="0" beatcount="0" fx1send="0" fx2send="0" interpqual="0" playthru="0" padnote="0" deftemplate="1" recpresetlen="0" recquant="3" recinput="0" recusethres="0" recthresh="-20000" recmonoutbus="0"/>
            <slices/>
        </cell>
        <cell row="2" column="4" layer="0" filename="" type="samtempl">
            <params gaindb="0" pitch="0" panpos="0" samtrigtype="0" loopmode="0" loopmodes="0" midimode="0" midioutchan="0" reverse="0" cellmode="0" envattack="0" envdecay="0" envsus="1000" envrel="200" quantsize="3" synctype="5" outputbus="0" polymode="0" slicestepmode="0" chokegrp="0" dualfilcutoff="0" rootnote="0" beatcount="0" fx1send="0" fx2send="0" interpqual="0" playthru="0" padnote="0" deftemplate="1" recpresetlen="0" recquant="3" recinput="0" recusethres="0" recthresh="-20000" recmonoutbus="0"/>
            <slices/>
        </cell>
        <cell row="3" column="4" layer="0" filename="" type="samtempl">
            <params gaindb="0" pitch="0" panpos="0" samtrigtype="0" loopmode="0" loopmodes="0" midimode="0" midioutchan="0" reverse="0" cellmode="0" envattack="0" envdecay="0" envsus="1000" envrel="200" quantsize="3" synctype="5" outputbus="0" polymode="0" slicestepmode="0" chokegrp="0" dualfilcutoff="0" rootnote="0" beatcount="0" fx1send="0" fx2send="0" interpqual="0" playthru="0" padnote="0" deftemplate="1" recpresetlen="0" recquant="3" recinput="0" recusethres="0" recthresh="-20000" recmonoutbus="0"/>
            <slices/>
        </cell>
        <cell row="0" column="0" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="1" column="0" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="2" column="0" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="3" column="0" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="0" column="1" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="1" column="1" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="2" column="1" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="3" column="1" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="0" column="2" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="1" column="2" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="2" column="2" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="3" column="2" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="0" column="3" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="1" column="3" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="2" column="3" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="3" column="3" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="0" column="4" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="1" column="4" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="2" column="4" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="3" column="4" layer="1" type="noteseq">
            <params notesteplen="10" notestepcount="16" dutycyc="1000" midioutchan="0" quantsize="1" padnote="0" dispmode="1" seqplayenable="0" seqstepmode="1"/>
            <sequence/>
        </cell>
        <cell row="0" column="0" layer="2" name="Section 1" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="1" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="2" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="3" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="4" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="5" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="6" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="7" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="8" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="9" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="10" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="11" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="12" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="13" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="14" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="15" column="0" layer="2" name="" type="section">
            <params sectionlenbars="8"/>
            <sequence/>
        </cell>
        <cell row="0" layer="3" type="delay">
            <params delaymustime="6" feedback="400" dealybeatsync="1" delay="400"/>
        </cell>
        <cell row="1" layer="3" type="reverb">
            <params decay="600" predelay="40" damping="500"/>
        </cell>
        <cell row="2" layer="3" type="filter">
            <params cutoff="600" res="400" filtertype="0" fxtrigmode="0"/>
        </cell>
        <cell row="3" layer="3" type="bitcrusher">
            <params/>
        </cell>
        <cell type="song">
            <params globtempo="120" songmode="0" sectcount="1" sectloop="1" swing="50" keymode="1" keyroot="3"/>
        </cell>
    </session>
</document>'''.format(
            sounds_info
        )

        return contents
