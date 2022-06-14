import logging
import os
import random
import re
import json
import time

import freesound

from api_key import API_KEY
from argparse import ArgumentParser
from helpers import DownloadAndConvertSoundsThread, SourceExporter, BlackboxExporter


logger = logging.getLogger()

freesound_client = freesound.FreesoundClient()
freesound_client.set_token(API_KEY)

available_preset_types = ['instrument', '16pad', 'loops']
available_exporters = ['source', 'blackbox']


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

    # Below are hardcoded manual fixes for sounds that are wrongly labeled in Freesound, I should contact sound author to fix that
    if sound.id == 65755:
        name = name.replace('A2', 'A1')
    elif sound.id == 65754:
        name = name.replace('A#2', 'A#1')
    elif sound.id == 65756:
        name = name.replace('B2', 'B1')

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
    return 0


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
    data['filesize'] = sound.filesize
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

def download_sounds(sounds, use_converted_files):
    for sound in sounds:
        logger.debug('{}'.format(sound['id']))
        dw_thread = DownloadAndConvertSoundsThread(sound['preview_url'], sound['id'], convert=use_converted_files)
        dw_thread.start()
        dw_thread.join()  # Wait until download finishes, we don't support async downloads (yet)

def make_instrument_preset_from_pack(pack_id, max_sounds_to_use=128, use_original_files=False, use_converted_files=False, include_sounds=False, max_velocity_layers=4):
    fs_fields_param = "id,previews,license,name,username,analysis,type,filesize,tags,duration,description"
    fs_descriptors_param = "rhythm.onset_times"

    # Get sounds info
    query_cache_filepath = f'.{pack_id}-{max_sounds_to_use}-{use_original_files}-{use_converted_files}-{include_sounds}-{max_velocity_layers}-query-cache.json'
    if False and os.path.exists(query_cache_filepath) and os.path.getmtime(query_cache_filepath) > time.time() - 3 * 3600:
        # If query cache exists and is not older than 3 hours, use that instead of making new query
        logger.info('- Getting pack info and preparing sounds (using cached results)')
        sounds = json.load(open(query_cache_filepath))
    else:
        logger.info('- Getting pack info and preparing sounds')
        pack = freesound_client.get_pack(pack_id)
        all_results = []
        results = pack.get_sounds(fields=fs_fields_param, descriptors=fs_descriptors_param, page_size=150)
        all_results += results
        while results.next is not None:
            results = results.next_page()
            all_results += results 
        sounds = [prepare_sound(result, use_original=use_original_files, use_converted=use_converted_files) for result in all_results]
        json.dump(sounds, open(query_cache_filepath, 'w'))
    logger.info('- Found {} sounds!'.format(len(sounds)))

    # Filter out sounds that have no midi_note information
    sounds = [sound for sound in sounds if 'midi_note' in sound]

    # Download the sounds
    if include_sounds:
        logger.info('- Downloading and converting sounds')
        download_sounds(sounds, use_converted_files=use_converted_files)
        
    # Keep only as many velocity layers as indicated
    midi_velocities = list(set([sound['midi_velocity'] for sound in sounds if 'midi_velocity' in sound]))
    n_vel_layers_used = 1
    if len(set(midi_velocities)) > 1:
        # Keep the N layers with higher values
        min_velocity_to_use = sorted(midi_velocities)[max(0, len(midi_velocities) - max_velocity_layers)]
        n_vel_layers_used = sum([1 for vel in midi_velocities if vel >= min_velocity_to_use])
        sounds = [sound for sound in sounds if sound['midi_velocity'] >= min_velocity_to_use or 'midi_velocity' not in sound]
    logger.info('- Will use {} velocity layers'.format(n_vel_layers_used))
    
    # Remove potential midi_note/midi_velocity duplicates
    already_used_notes = []
    filtered_sounds = []
    removed_notes = 0
    for sound in sounds:
        key = str(sound['midi_note']) + '_' + str(sound.get('midi_velocity', 0))
        if key not in already_used_notes:
            filtered_sounds.append(sound)
            already_used_notes.append(key)
        else:
            removed_notes += 1
    sounds = filtered_sounds
    logger.info('- Removed {} redundant notes'.format(removed_notes))

    # Keep only a specific number of notes to be below the maximum number of sounds
    num_notes_to_keep = 0
    for i in range(0, max_sounds_to_use, n_vel_layers_used):
        num_notes_to_keep += 1
    all_notes = sorted(list(set([sound['midi_note'] for sound in sounds])))
    if num_notes_to_keep < len(all_notes):
        n_notes_to_remove = len(all_notes) - num_notes_to_keep
        n_sounds_to_remove = n_notes_to_remove * n_vel_layers_used
        logger.info('- Removing {} sounds ({} notes) because exceeding max'.format(n_sounds_to_remove, n_notes_to_remove))
        notes_to_remove = []
        index = 0
        while len(notes_to_remove) < n_notes_to_remove:
            notes_to_remove.append(int(index * 127/n_notes_to_remove))
            index += 1
        sounds = [sound for sound in sounds if sound['midi_note'] not in notes_to_remove]

    logger.info('- {} notes selected with {} velocity layers ({} sounds)'.format(num_notes_to_keep, n_vel_layers_used, len(sounds)))
    return sounds

def make_16pad_preset_from_query(query, use_original_files=False, use_converted_files=False, include_sounds=False, max_duration=0.5):
    fs_fields_param = "id,previews,license,name,username,analysis,type,filesize,tags,duration,description"
    fs_descriptors_param = "rhythm.onset_times"

    # Search for sounds and select 16
    results = freesound_client.text_search(query=query, filter='duration:[0 TO {}]'.format(str(max_duration)), fields=fs_fields_param, descriptors=fs_descriptors_param, page_size=150)
    results_list = [r for r in results if hasattr(r, 'analysis')]
    sounds = [prepare_sound(result, use_original=use_original_files, use_converted=use_converted_files) for result in random.sample(results_list, 16)]
    
    # Download the sounds
    if include_sounds:
        logger.info('- Downloading and converting sounds')
        download_sounds(sounds, use_converted_files=use_converted_files)

    return sounds

def make_loops_preset_from_query(query, use_original_files=False, use_converted_files=False, include_sounds=False):
    return make_16pad_preset_from_query(query, use_original_files=use_original_files, use_converted_files=use_converted_files, include_sounds=include_sounds, max_duration=10)

if __name__ == '__main__':
    parser = ArgumentParser(description="""
    Freesound Presets. Generates sampler presets based on Freesound sounds and exports them in differen sampler formats.""")
    parser.add_argument('-v', '--verbose', help='if set, prints detailed info on screen', action='store_const', const=True, default=False)
    parser.add_argument('-e', '--exporter', help='one of {}'.format(str(available_exporters)), required=True)
    parser.add_argument('-t', '--type', help='one of {}'.format(str(available_preset_types)), required=True)
    parser.add_argument('-p', '--pack', help='Freesound pack ID to get instrument samples from', default=None)
    parser.add_argument('-q', '--query', help='Textual query for 16pad presets', default=None)
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
        logger.info('*** Creating {} preset {}'.format(args.type, args.name))
        sounds = make_instrument_preset_from_pack(pack_id, use_original_files=args.originals, use_converted_files=args.convert, include_sounds=args.include_sounds)

    elif args.type == '16pad':
        logger.info('*** Creating {} preset {}'.format(args.type, args.name))
        sounds = make_16pad_preset_from_query(args.query, use_original_files=args.originals, use_converted_files=args.convert, include_sounds=args.include_sounds)

    elif args.type == 'loops':
        logger.info('*** Creating {} preset {}'.format(args.type, args.name))
        sounds = make_loops_preset_from_query(args.query, use_original_files=args.originals, use_converted_files=args.convert, include_sounds=args.include_sounds)


    if args.exporter == 'source':
        if args.loop:
            sound_overwrite_exporter_fields = [{'launchMode': 1} for sound in sounds]
        else:
            sound_overwrite_exporter_fields = [{'launchMode': 0} for sound in sounds]
        SourceExporter(
            sounds=sounds, 
            sound_overwrite_exporter_fields=sound_overwrite_exporter_fields, 
            preset_name=args.name, 
            ptype=args.type,
            include_sounds=args.include_sounds).export()

    elif args.exporter == 'blackbox':
        if args.type == 'loops':
            sound_overwrite_exporter_fields = [{
                'stype': 'sample',
                'samtrigtype': 2,
                'loopmode': 1,
                'cellmode': 1} for sound in sounds]
        else:
            sound_overwrite_exporter_fields = None
        BlackboxExporter(
            sounds=sounds, 
            sound_overwrite_exporter_fields=sound_overwrite_exporter_fields, 
            preset_name=args.name, 
            ptype=args.type,
            include_sounds=args.include_sounds).export()
