import sys,json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import patch_state
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
base='http://127.0.0.1:8080'
with urlopen(base+'/api/state') as r: original=json.load(r)
errors=[]
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':1920,'height':1080})
  # Exercise bundled fonts and functional scripts without optional Google Fonts.
  context.route('https://fonts.googleapis.com/**',lambda route:route.abort())
  pages={}
  for name in original['screens']:
   page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
   page.goto(base+'/'+name,wait_until='domcontentloaded')
   page.wait_for_function("document.querySelector('iframe')?.style.visibility === 'visible'")
   frame=page.frames[-1]
   assert frame.locator('#stage').count()==1,name
   if name == 'intermission':
    assert frame.locator('.band, #nl, #nx, #run').count() == 0
   pages[name]=page
  page=pages['intermission'];document_id=page.evaluate('window.testMarker=123;window.testMarker')
  patch_state({'screens':{'intermission':{'footer':'LIVE GAME 5'}}})
  page.wait_for_function("document.querySelector('iframe')?.contentDocument?.querySelector('#footer')?.textContent === 'LIVE GAME 5'")
  assert page.evaluate('window.testMarker')==123,'OBS source reloaded'
  assert pages['starting-soon'].frames[-1].locator('#stage').count()==1
  patch_state({'global':{'colors':{'red':'#123456'}}})
  for name,page in pages.items():
   page.wait_for_function("getComputedStyle(document.querySelector('iframe').contentDocument.documentElement).getPropertyValue('--red').trim() === '#123456'")
  # Control panel must actually write shared state and propagate it to rendered text.
  control=context.new_page();control.goto(base+'/control')
  control.locator('#links a').first.wait_for()
  assert control.locator('#links a[href="https://apex.praxidike.space/intermission"]').count() == 1
  control.get_by_text('Advanced JSON editor',exact=True).click()
  control.locator('#editor').fill(json.dumps({'colors':{'red':'#123456'},'footer':'BROWSER LIVE'}))
  control.locator('#apply').click();control.get_by_text('Saved. OBS pages update automatically.',exact=True).wait_for()
  pages['intermission'].wait_for_function("document.querySelector('iframe')?.contentDocument?.querySelector('#footer')?.textContent === 'BROWSER LIVE'")
  control.locator('#autoWeek').uncheck()
  control.locator('#season').fill('SPRING 2027')
  control.locator('#week').fill('2')
  control.locator('#phase').fill('REGULAR SEASON')
  control.locator('#broadcast').click()
  control.get_by_text('Season and week updated on all screens.', exact=True).wait_for()
  patch_state({'global': {'mapName': 'Olympus'}})
  pages['intermission'].wait_for_function("document.querySelector('iframe')?.contentDocument?.querySelector('#kick')?.textContent.includes('SPRING 2027')")
  pages['ingame-overlay'].wait_for_function("document.querySelector('iframe')?.contentDocument?.querySelector('#ev')?.textContent === 'SPRING 2027 WEEK 2 // Olympus'")
  pages['starting-soon'].wait_for_function("document.querySelector('iframe')?.contentDocument?.querySelector('#sideL')?.textContent.includes('WEEK 2')")
  pages['stream-ending'].wait_for_function("document.querySelector('iframe')?.contentDocument?.querySelector('#side')?.textContent.includes('SPRING 2027 // WEEK 2')")
  assert not errors, errors
  browser.close()
 print('PASS: all six screens rendered without JS errors; Python screen patch, global colors, control UI edits and shared season/week/map labels propagated without OBS source reload')
finally:
 current=json.load(urlopen(base+'/api/state'))
 reset={k:None for k in current['global'] if k not in original['global']}
 reset.update(original['global'])
 patch_state({'global':reset,'screens':original['screens']})
