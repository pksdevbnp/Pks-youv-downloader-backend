
const u = document.getElementById('u');
const go = document.getElementById('go');
const clearBtn = document.getElementById('clear');
const qSel = document.getElementById('q');
const btnMp4 = document.getElementById('mp4');
const btnMp3 = document.getElementById('mp3');
const list = document.getElementById('list');
const subsList = document.getElementById('subs');
const thumb = document.getElementById('thumb');
const titleEl = document.getElementById('title');
const metaEl = document.getElementById('meta');
const statusEl = document.getElementById('status');

// tabs
document.querySelectorAll('.tab').forEach(t => {
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('sec-' + t.dataset.tab).classList.add('active');
  });
});

function fmtSize(bytes){
  if(!bytes) return '';
  const units=['B','KB','MB','GB']; let i=0, v=bytes;
  while(v>1024 && i<units.length-1){ v/=1024; i++; }
  return v.toFixed(1)+' '+units[i];
}

function copy(text){
  navigator.clipboard?.writeText(text);
  statusEl.textContent = 'Copied to clipboard';
  setTimeout(()=>statusEl.textContent='',1500);
}

async function fetchInfo(){
  const url = u.value.trim();
  if(!url) return alert('Paste a valid URL');
  statusEl.textContent = 'Fetching info...';
  list.innerHTML = 'Loading...';
  subsList.innerHTML = '';
  thumb.style.display = 'none'; titleEl.textContent=''; metaEl.textContent='';

  const res = await fetch(`${window.BACKEND_BASE}/api/info`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({url})
  });
  if(!res.ok){ list.innerHTML = 'Error fetching info'; statusEl.textContent=''; return; }
  const data = await res.json();

  titleEl.textContent = data.title || '';
  metaEl.textContent = data.channel || '';
  if(data.thumbnail){ thumb.src = data.thumbnail; thumb.style.display = 'block'; }
  statusEl.textContent = '';

  // formats
  list.innerHTML = '';
  (data.formats || []).slice(0, 60).forEach(f => {
    const row = document.createElement('div');
    row.className = 'item';
    const left = document.createElement('div');
    left.innerHTML = `<b>${f.quality || ''}</b> <small>${f.ext || ''}</small>`;

    const right = document.createElement('div');
    const size = document.createElement('small'); size.textContent = fmtSize(f.filesize);
    const a1 = document.createElement('a'); a1.href = f.url; a1.textContent='Direct'; a1.className='btn'; a1.setAttribute('download','');
    const a2 = document.createElement('a'); a2.href = `${window.BACKEND_BASE}/api/download?url=${encodeURIComponent(url)}&format_id=${encodeURIComponent(f.format_id)}&filename=${encodeURIComponent((data.title||'video') + '.' + (f.ext||'mp4'))}`; a2.textContent='Server'; a2.className='btn';
    const cp = document.createElement('a'); cp.textContent='Copy'; cp.className='btn copy'; cp.href='#'; cp.onclick=(e)=>{e.preventDefault(); copy(f.url)};

    right.appendChild(size); right.appendChild(document.createTextNode(' '));
    right.appendChild(a1); right.appendChild(document.createTextNode(' | '));
    right.appendChild(a2); right.appendChild(document.createTextNode(' | '));
    right.appendChild(cp);

    row.appendChild(left); row.appendChild(right);
    list.appendChild(row);
  });

  // subtitles
  subsList.innerHTML = '';
  (data.subtitles || []).forEach(s => {
    const row = document.createElement('div'); row.className='item';
    row.innerHTML = `<div><b>${s.lang}</b> <small>.${s.ext||''}</small></div>`;
    const right = document.createElement('div');
    const a = document.createElement('a'); a.href = s.url; a.textContent='Download'; a.className='btn'; a.setAttribute('download','');
    const cp = document.createElement('a'); cp.href='#'; cp.textContent='Copy'; cp.className='btn copy'; cp.onclick=(e)=>{e.preventDefault(); copy(s.url)};
    right.appendChild(a); right.appendChild(document.createTextNode(' | ')); right.appendChild(cp);
    row.appendChild(right); subsList.appendChild(row);
  });

  // server merge buttons
  btnMp4.onclick = () => {
    const h = qSel.value;
    const dl = `${window.BACKEND_BASE}/api/grab_mp4?url=${encodeURIComponent(url)}&height=${encodeURIComponent(h)}&filename=${encodeURIComponent((data.title||'video')+'.mp4')}`;
    window.open(dl, '_blank');
  };
  btnMp3.onclick = () => {
    const dl = `${window.BACKEND_BASE}/api/grab_mp3?url=${encodeURIComponent(url)}&filename=${encodeURIComponent((data.title||'audio')+'.mp3')}`;
    window.open(dl, '_blank');
  };
}

go.addEventListener('click', fetchInfo);
clearBtn.addEventListener('click', () => {
  u.value=''; list.innerHTML=''; subsList.innerHTML=''; thumb.style.display='none'; titleEl.textContent=''; metaEl.textContent=''; statusEl.textContent='Cleared';
  setTimeout(()=>statusEl.textContent='',800);
});
