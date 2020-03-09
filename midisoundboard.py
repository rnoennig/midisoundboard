import os
import sys
import queue
import jack
import soundfile as sf
import threading

# config

BASE_DIRECTORY = '/mnt/storage/MyMusic/soundboard'

client = jack.Client('MidiBoard')
blocksize = client.blocksize
samplerate = client.samplerate

midiport = client.midi_inports.register('midi_in')
audioport_1 = client.outports.register('audio_out1')
audioport_2 = client.outports.register('audio_out2')

# main

NOTEON = 0x9
NOTEOFF = 0x8

fs = None
buffersize = 20000

q = queue.Queue(maxsize=buffersize)
event = threading.Event()

def print_error(*args):
    print(*args, file=sys.stderr)

def note_to_file(note):
    try:
        fn = sorted(os.listdir(BASE_DIRECTORY), key=str.lower)[note-48]
        fp = BASE_DIRECTORY + '/' + fn
    except:
        fp = None
    return fp

def play_file(filename):
    with sf.SoundFile(filename) as f:
        print("playing file: " + str(f))
        block_generator = f.blocks(blocksize=blocksize, dtype='float32',
                                   always_2d=True, fill_value=0)
        for _, data in zip(range(buffersize), block_generator):
            q.put_nowait(data)  # Pre-fill queue

        print("putting data in queue")
        print(blocksize)
        print(samplerate)
        timeout = blocksize * buffersize / samplerate
        for data in block_generator:
            q.put(data, timeout=timeout)
        q.put(None, timeout=timeout)  # Signal end of file
        print("finished putting data in queue")

def play_note(note):
    fn = note_to_file(note)
    if fn:
        print(fn)
        play_file(fn)

def kill_note(note):
    global q
    q = queue.Queue(maxsize=buffersize)
    for port in client.outports:
        port.get_array().fill(0)
    print(note)

def stop_callback(msg=''):
    if msg:
        print_error(msg)
    for port in client.outports:
        port.get_array().fill(0)
    event.set()
    raise jack.CallbackExit

@client.set_xrun_callback
def xrun(delay):
    print_error("An xrun occured, increase JACK's period size?")
    
@client.set_process_callback
def process(frames):
    """Main callback."""
    events = {}
    try:
        for offset, data in midiport.incoming_midi_events():
            if len(data) == 3:
                status, pitch, vel = bytes(data)
                # MIDI channel number are the first 4 bits
                channel = status & int('1111', 2)
                # shift channel bits
                status >>= 4
                if channel == 0:
                    if status == NOTEON:
                        play_note(pitch)
                    elif status == NOTEOFF:
                        kill_note(pitch)
                else:
                    pass  # ignore
    except Exception as e:
        print_error("Something went wrong: " + str(e))
    # play audio
    if frames != blocksize:
        stop_callback('blocksize must not be changed, I quit!')

    data = None
    try:
        data = q.get_nowait()
    except queue.Empty:
        # queue empty
        pass
    if data is None:
        # playback is finished
        pass
    else:
        for channel, port in zip(data.T, client.outports):
            port.get_array()[:] = channel

@client.set_shutdown_callback
def shutdown(status, reason):
    print('JACK shutdown:', reason, status)
    event.set()

with client:
    print('Press Ctrl+C to stop')
    try:
        event.wait()
    except KeyboardInterrupt:
        print('\nInterrupted by user')
