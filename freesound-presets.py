import logging
import os
import re

import freesound

from api_key import API_KEY
from argparse import ArgumentParser
from helpers import DownloadAndConvertSoundsThread, SourceExporter


logger = logging.getLogger()

freesound_client = freesound.FreesoundClient()
freesound_client.set_token(API_KEY)

available_preset_types = ['instrument']


def note_name_to_number(note_name):
    """Converts a note name in the format
    ``'(note)(accidental)(octave number)'`` (e.g. ``'C#4'``) to MIDI note
    number.
    ``'(note)'`` is required, and is case-insensitive.
    ``'(accidental)'`` should be ``''`` for natural, ``'#'`` for sharp and
    ``'!'`` or ``'b'`` for flat.
    If ``'(octave)'`` is ``''``, octave 0 is assumed.
    Parameters
    ----------
    note_name : str
        A note name, as described above.
    Returns
    -------
    note_number : int
        MIDI note number corresponding to the provided note name.
    Notes
    -----
        Thanks to Brian McFee.
    """
    # Copied from https://github.com/craffel/pretty-midi

    # Map note name to the semitone
    pitch_map = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
    # Relative change in semitone denoted by each accidental
    acc_map = {'#': 1, '': 0, 'b': -1, '!': -1}

    # Reg exp will raise an error when the note name is not valid
    try:
        # Extract pitch, octave, and accidental from the supplied note name
        match = re.match(r'^(?P<n>[A-Ga-g])(?P<off>[#b!]?)(?P<oct>[+-]?\d+)$',
                         note_name)

        pitch = match.group('n').upper()
        offset = acc_map[match.group('off')]
        octave = int(match.group('oct'))
    except Exception as e:
        raise ValueError('Improper note format: {}'.format(note_name))

    # Convert from the extrated ints to a full note number
    return 12*(octave + 1) + pitch_map[pitch] + offset


def get_midi_note(sound):

    # Try finding "standard" tag of patter midi-note-X
    for tag in sound.tags:
        if 'midi-note-' in tag:
            return int(tag.split('midi-note-')[1])

    # Try finding "standard" annotation in description (eg used for good sounds)
    if 'midi note::' in sound.description:
        try:
            return int(sound.description.split('midi note::')[1].split('\n')[0])
        except Exception as e:
            pass
    
    # Try finding note names in tags (more error prone?)
    for tag in sound.tags:
        try:
            return note_name_to_number(tag)
        except ValueError:
            pass

    # Try finding note names in tokenized sound name
    name = sound.name
    name_parts = name.replace('-', ' ').replace('_', ' ').replace('.', ' ').split(' ')
    for name_part in name_parts:
        try:
            return note_name_to_number(name_part)
        except ValueError as e:
            pass

    return None


def get_midi_velocity(sound):
    for tag in sound.tags:
        if 'midi-velocity-' in tag:
            return int(tag.split('midi-velocity-')[1])
    return None


def get_effective_start_time(sound):
    if hasattr(sound, 'analysis'):
        if hasattr(sound.analysis, 'rhythm'):
            if hasattr(sound.analysis.rhythm, 'onset_times'):
                if type(sound.analysis.rhythm.onset_times) == float:
                    return sound.analysis.rhythm.onset_times
                else:
                    return float(sound.analysis.rhythm.onset_times[0])
    return None


def prepare_sound(sound, use_original=False, use_converted=False):
    logger.debug('- Preparing sound {}'.format(sound.id)) 
    data = {}

    if use_converted:
        path = 'audio/{}.wav'.format(sound.id)
    else:
        if use_original:
            path = '/app/audio/{}.{}'.format(sound.id, sound.type)
        else:
            path = '/app/audio/{}.ogg'.format(sound.id)

    data['path'] = path
    data['id'] = sound.id
    data['type'] = sound.type
    data['name'] = sound.name
    data['license'] = sound.license    
    data['preview_url'] = sound.previews.preview_hq_ogg
    data['username'] = sound.username
    data['duration'] = float(sound.duration)
    data['start_time'] = get_effective_start_time(sound)
    data['start_percentage'] = data['start_time'] / data['duration']
    data['midi_note'] = get_midi_note(sound)
    data['midi_velocity'] = get_midi_velocity(sound)
    return {key: value for key, value in data.items() if value is not None}


def make_instrument_preset_from_pack(pack_id, max_sounds_to_use=64, use_original_files=False, use_converted_files=False, include_sounds=False):
    fs_fields_param = "id,previews,license,name,username,analysis,type,filesize,tags,duration,description"
    fs_descriptors_param = "rhythm.onset_times"
    
    # Get sounds info
    logger.info('- Getting pack info and preparing sounds')
    pack = freesound_client.get_pack(pack_id)
    results = pack.get_sounds(fields=fs_fields_param, descriptors=fs_descriptors_param, page_size=150)
    sounds = [prepare_sound(result, use_original=use_original_files, use_converted=use_converted_files) for result in results]
    
    # Download the sounds
    logger.info('- Downloading and converting sounds')
    if include_sounds:
        for sound in sounds:
            logger.debug('{}'.format(sound['id']))
            dw_thread = DownloadAndConvertSoundsThread(sound['preview_url'], sound['id'], convert=use_converted_files)
            dw_thread.start()
            dw_thread.join()  # Wait until download finishes, we don't support async downloads (yet)
        
    # Keep only one velocity layer
    logger.info('- Removing redundant velocity layers')
    midi_velocities = [sound['midi_velocity'] for sound in sounds if 'midi_velocity' in sound]
    if len(set(midi_velocities)) > 1:
        # More than one layer, choose the highest
        velocity_to_use = max(midi_velocities)
        sounds = [sound for sound in sounds if sound['midi_velocity'] == velocity_to_use or 'midi_velocity' not in sound]
    
    # Remove potential midi_note duplicates
    logger.info('- Removing redundant notes')
    already_used_notes = []
    filtered_sounds = []
    for sound in [sound for sound in sounds if 'midi_note' in sound]:
        if sound['midi_note'] not in already_used_notes:
            filtered_sounds.append(sound)
            already_used_notes.append(sound['midi_note'])
    sounds = filtered_sounds

    # Remove some notes if using more than the limit
    if len(sounds) > max_sounds_to_use:
        n_to_remove = abs(max_sounds_to_use - len(sounds))
        logger.info('- Removing {} sounds because exceeding max'.format(n_to_remove))
        positions_to_remove = list(range(0, len(sounds), len(sounds) // n_to_remove))
        positions_to_remove = positions_to_remove[:n_to_remove]
        filtered_sounds = []
        for i in range(0, len(sounds)):
            if i not in positions_to_remove:
                filtered_sounds.append(sounds[i])
        sounds = filtered_sounds

    # Calculate midi note ranges
    logger.info('- Calculating midi note ranges')
    sounds = sorted(sounds, key=lambda x: x['midi_note'])
    last_midi_note_covered = 0
    for (current_sound, next_sound) in zip(sounds, sounds[1:] + [None]):
        if next_sound is not None:
            end_midi_note_range = current_sound['midi_note'] + (next_sound['midi_note'] - current_sound['midi_note']) // 2
            midi_notes = list(range(last_midi_note_covered, end_midi_note_range))  
            last_midi_note_covered = end_midi_note_range
        else:
            midi_notes = list(range(last_midi_note_covered, 128))  
        current_sound['midi_notes'] = sorted(list(set(midi_notes)))
    all_midi_notes = []
    for sound in sounds:
        all_midi_notes += sound['midi_notes']
    assert (len(all_midi_notes) == len(set(all_midi_notes))), "Duplicated midi notes found..."
        
    return sounds   


if __name__ == '__main__':
    parser = ArgumentParser(description="""
    Freesound Presets. Generates sampler presets based on Freesound sounds and exports them in differen sampler formats.""")
    parser.add_argument('-v', '--verbose', help='if set, prints detailed info on screen', action='store_const', const=True, default=False)
    parser.add_argument('-t', '--type', help='one of {}'.format(str(available_preset_types)), required=True)
    parser.add_argument('-p', '--pack', help='Freesound pack ID to get instrument samples from', default=None)
    parser.add_argument('-l', '--loop', help='configure sounds to loop', action='store_const', const=True, default=False)
    parser.add_argument('-n', '--name', help='name for the output preset', required=True)
    parser.add_argument('-i', '--include-sounds', help='include sound files with the preset', action='store_const', const=True, default=False)
    parser.add_argument('-c', '--convert', help='convert included sound files to WAV', action='store_const', const=True, default=False)
    parser.add_argument('-o', '--originals', help='use original sound files when downloading', action='store_const', const=True, default=False)
    
    args = parser.parse_args()
    logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO if not args.verbose else logging.DEBUG)

    assert (args.type in available_preset_types), 'Wrong preset type, must be one of {}'.format(str(available_preset_types))
    
    if args.type == 'instrument':
        assert (args.pack), 'When creating an instrument preset, you must provide --pack parameter with the pack ID'
        try:
            pack_id = int(args.pack)
        except ValueError:
            raise Exception('Invalid --pack parameter, must be an integer')
        logger.info('Creating {} preset {}'.format(args.type, args.name))
        sounds = make_instrument_preset_from_pack(pack_id, use_original_files=args.originals, use_converted_files=args.convert, include_sounds=args.include_sounds)
        SourceExporter(sounds=sounds, loop=args.loop, preset_name=args.name, include_sounds=args.include_sounds).export()
