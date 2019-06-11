#!/usr/bin/env python
from flask import Flask, render_template, request, redirect, url_for

import alsaaudio
import pafy
import requests
import socket
import threading
import time
import vlc

# TODO
# volume improvements
# skip should be able to skip to autoplay if nothing in queue
# add a stop command to stop whatever is currently playing
# autoplay needs to be worked on so it doesn't repeat, currently repeats after a few songs
# running the skip command breaks the queue for some reason, look into this

app = Flask(__name__)

HOST = "0.0.0.0"
PORT = 8080

CMDLET = "---> "

vlc_instance = ""
player = ""
mixer = ""
queue = []
current_vid = ""
autoplay = ""
connections = []
active_timer = ""

### Maybe use if web sockets get added
#def send(conn, msg="", cmdlet=True):
#    if not cmdlet:
#        conn.sendall("%s\n" % (msg))
#        if "Welcome" not in msg:
#            send(conn)
#    else:
#        conn.sendall("\n%s" % (CMDLET))
#
#def send_help(conn):
#    HELPMSG = """The following commands exist:
#    \tplay <YouTube URL>\t- Adds a song to the queue.
#    \tplaynow <YouTube URL>\t- Stops the current song and plays the requested URL.
#    \tskip\t\t\t- Skips the current song and moves to the next one.
#    \tqueue\t\t\t- Shows the current song queue.
#    \tvol <0-100>\t\t- Sets the volume level.
#    \thelp\t\t\t- Shows this help message.
#    \texit\t\t\t- Exits this PiPlay connection.\n"""
#    conn.sendall(HELPMSG)

def _grab_autoplay(conn, url):
    global autoplay
    html = requests.get(url).text

    # pull the URL from youtube's autoplay "up next" feature
    html = html[html.index("Up next"):]
    html = html[html.index("href"):html.index("href")+100]
    url = "https://www.youtube.com%s" % (html.split('"')[1])

    vid = pafy.new(url)
    autoplay = vid

## Play method, used in cycle
def play(conn, vid):
    global vlc_instance, player, connections, active_timer, current_vid
    try:
        # load url to stream in VLC
        stream = vid.getbest(preftype="webm")
        media = ""
        if stream is None:
            media = vlc_instance.media_new(vid.getbest().url)
        else:
            media = vlc_instance.media_new(stream.url)
        media.get_mrl()
        player.set_media(media)
        player.play()
        player.set_fullscreen(True)

        # keep track of when songs were started so that a playlist will only run for 6 minutes before moving on in the queue
        active_timer = time.time()

        # if there's nothing in the queue to play after this song, grab the autoplay up next from youtube
        if len(queue) == 0:
            _grab_autoplay(conn, vid.watchv_url)
        current_vid = vid
    except ValueError:
        if conn is not None:
            send(conn, "Invalid URL entered.", False)

## Cycle thread to keep videos playing
def cycle_queue():
    global player, queue, autoplay, active_timer

    # loop every 7 seconds checking queue
    while True:
        time.sleep(7)
        # if no song is playing and there is something in the queue, play it
        if player.is_playing() == 0 or (time.time() - active_timer > 360):
            if len(queue) > 0:
                play(None, queue.pop(0))
            else:
                # nothing is playing and queue is empty, close player
                if autoplay != "":  # skip if autoplay is its initial value of empty string
                    play(None, autoplay)

def init():
    global vlc_instance, player, connections, mixer
    vlc_instance = vlc.Instance()
    player = vlc_instance.media_player_new()
    mixer = alsaaudio.Mixer()
    print("PiPlay server initialized.")

### Flask Routes ###

@app.route('/', methods=['GET'])
def index():
    global mixer, queue, current_vid
    return render_template('index.html',
                           vol=mixer.getvolume()[0],
                           current=current_vid.title if current_vid is not "" else "", 
                           queue=[(i, v.title, v.duration)
                                  for i,v in enumerate(queue, start=1)])

@app.route('/play', methods=['POST'])
def play_ep():
    global queue, player
    url = str(request.form['yt'])
            
    if url is None or url is '':
        return "failure: error in URL"
    try:
        vid = pafy.new(url)
        # if queue is empty and player is off, play
        if len(queue) == 0 and player.is_playing() == 0:
            play(None, vid)
        else:
            # songs are queued or currently playing, add to queue
            queue.append(vid)
    except ValueError as e:
        return "Invalid URL entered: %s: %s" % (url, e)

    return redirect(url_for('index'))

@app.route('/playnow', methods=['POST'])
def playnow_ep():
    global queue, player
    url = str(request.form['yt'])
            
    if url is None or url is '':
        return "failure: error in URL"
    vid = pafy.new(url)
    play(None, vid)

    return redirect(url_for('index'))

@app.route('/vol', methods=['POST'])
def vol_ep():
    global mixer
    vol = int(request.form['vol'])

    try:
        if vol < 0 or vol > 100:
            return "Invalid volume setting"
        
        mixer.setvolume(vol)
    except ValueError:
        return "Setting Volume Failed"

    return redirect(url_for('index'))

@app.route('/skip', methods=['POST'])
def skip_ep():
    global queue, player

    if len(queue) > 0:
        play(None, queue.pop(0))

    return redirect(url_for('index'))

if __name__ == '__main__':
    init()
    t = threading.Thread(target=cycle_queue)
    t.start()
    app.run(debug=True, host=HOST, port=PORT)
