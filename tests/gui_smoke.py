"""Exercise operator controls on an isolated server; never modify on-air state."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temporary:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    process = subprocess.Popen([sys.executable, 'app.py'], cwd=ROOT,
        env={**os.environ, 'PORT': str(port), 'APEX_BIND': '127.0.0.1', 'APEX_STATE_FILE': temporary+'/state.json'},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def state():
        return json.load(urlopen(base+'/api/state', timeout=5))
    try:
        for attempt in range(50):
            try:
                state();break
            except OSError:
                time.sleep(.1)
        errors=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1080})
            page.on('pageerror',lambda error: errors.append(str(error)))
            page.goto(base+'/control')
            page.locator('#saveStaff').wait_for(state='visible')
            page.locator('#season').fill('SPRING TEST')
            page.locator('#week').fill('3')
            page.locator('#broadcast').click()
            page.get_by_text('Season and week updated on all screens.',exact=True).wait_for()
            assert state()['global']['week']==3
            page.locator('#token').fill('weekly-ui-test-token')
            page.locator('#saveToken').click()
            page.get_by_text('Weekly token saved. Previous-week scores cleared.',exact=True).wait_for()
            assert state()['global']['statsTokens']==['weekly-ui-test-token']
            assert page.locator('#token').input_value()==''
            page.locator('#staff .staff-row').nth(2).locator('textarea').fill('Producer One\nProducer Two')
            page.locator('#addStaff').click()
            row=page.locator('#staff .staff-row').last
            row.locator('input').fill('REPLAY OPERATOR')
            row.locator('textarea').fill('Replay Person')
            page.locator('#saveStaff').click()
            page.get_by_text('Production staff saved. Ending credits update live.',exact=True).wait_for()
            assert state()['screens']['stream-ending']['credits'][2]['names']==['Producer One','Producer Two']
            assert state()['screens']['stream-ending']['credits'][-1]['role']=='REPLAY OPERATOR'
            page.locator('#scope').select_option('intermission')
            page.locator('#fields').get_by_label('Timer Label',exact=True).fill('RETURNING IN')
            page.locator('#fields').get_by_label('Show Trivia',exact=True).uncheck()
            page.locator('#saveFields').click()
            page.get_by_text('Fields saved. OBS pages update automatically.',exact=True).wait_for()
            assert state()['screens']['intermission']['timerLabel']=='RETURNING IN'
            assert state()['screens']['intermission']['showTrivia'] is False
            # Generic array controls: edit a caster and add another without JSON.
            page.locator('#scope').select_option('ingame-overlay')
            page.locator('#fields summary').filter(has_text='Casters (').click()
            page.locator('#fields').get_by_label('Casters item',exact=True).first.fill('Caster One')
            page.get_by_role('button',name='Add Casters item',exact=True).click()
            page.locator('#fields').get_by_label('Casters item',exact=True).last.fill('Caster Two')
            page.locator('#saveFields').click()
            page.get_by_text('Fields saved. OBS pages update automatically.',exact=True).wait_for()
            assert state()['screens']['ingame-overlay']['casters'][-1]=='Caster Two'
            page.reload()
            page.locator('#staff textarea').nth(2).wait_for()
            assert page.locator('#week').input_value()=='3'
            assert page.locator('#staff textarea').nth(2).input_value()=='Producer One\nProducer Two'
            assert not errors,errors
            browser.close()
        print('PASS: GUI week, weekly token, production roles/names, text fields, switches, lists and reload persistence; isolated operator state')
    finally:
        process.terminate()
        process.wait(timeout=10)
