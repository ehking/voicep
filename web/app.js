const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const selectFileBtn = document.getElementById('select-file');
const statusIndicator = document.getElementById('status-indicator');
const statusText = document.getElementById('status-text');
const spinner = document.getElementById('spinner');
const progressBar = document.getElementById('progress-bar');
const progressLabel = document.getElementById('progress-label');
const resultText = document.getElementById('result-text');
const toggleClean = document.getElementById('toggle-clean');
const toggleRaw = document.getElementById('toggle-raw');
const copyBtn = document.getElementById('copy-btn');
const downloadBtn = document.getElementById('download-btn');
const historyList = document.getElementById('history-list');
const refreshHistoryBtn = document.getElementById('refresh-history');
const toast = document.getElementById('toast');

let currentJobId = null;
let currentResult = { raw_text: '', cleaned_text: '' };
let showClean = true;
let pollInterval = null;

function showToast(message, type = 'info') {
  toast.textContent = message;
  toast.classList.remove('opacity-0', 'pointer-events-none');
  toast.classList.remove('bg-green-600', 'bg-red-600', 'bg-gray-800');
  toast.classList.add(type === 'error' ? 'bg-red-600' : type === 'success' ? 'bg-green-600' : 'bg-gray-800');
  setTimeout(() => {
    toast.classList.add('opacity-0', 'pointer-events-none');
  }, 3000);
}

function setStatus(status, progress) {
  const statusMap = {
    queued: 'در صف',
    processing: 'در حال پردازش',
    done: 'انجام شد',
    error: 'خطا'
  };
  statusIndicator.className = 'w-3 h-3 rounded-full ' + (status === 'done' ? 'bg-green-500' : status === 'error' ? 'bg-red-500' : 'bg-yellow-400');
  statusText.textContent = statusMap[status] || status;
  spinner.classList.toggle('hidden', status !== 'processing');
  progressBar.style.width = `${progress || 0}%`;
  progressLabel.textContent = `${progress || 0}%`;
}

function updateResultView() {
  resultText.value = showClean ? (currentResult.cleaned_text || '') : (currentResult.raw_text || '');
  toggleClean.classList.toggle('bg-indigo-600', showClean);
  toggleClean.classList.toggle('text-white', showClean);
  toggleClean.classList.toggle('bg-gray-200', !showClean);
  toggleClean.classList.toggle('text-gray-800', !showClean);
  toggleRaw.classList.toggle('bg-indigo-600', !showClean);
  toggleRaw.classList.toggle('text-white', !showClean);
  toggleRaw.classList.toggle('bg-gray-200', showClean);
  toggleRaw.classList.toggle('text-gray-800', showClean);
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  setStatus('queued', 5);
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (!data.ok) {
      throw new Error(data.error?.message || 'خطا در آپلود');
    }
    currentJobId = data.job.id;
    showToast('فایل دریافت شد و در صف قرار گرفت', 'success');
    startPolling();
    loadHistory();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(checkStatus, 1500);
}

async function checkStatus() {
  if (!currentJobId) return;
  try {
    const res = await fetch(`/api/jobs/${currentJobId}`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error?.message || 'خطا در وضعیت');
    const job = data.job;
    setStatus(job.status, job.progress);
    if (job.status === 'done') {
      clearInterval(pollInterval);
      await loadResult();
    } else if (job.status === 'error') {
      clearInterval(pollInterval);
      showToast(job.error_message || 'خطا در پردازش', 'error');
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function loadResult(jobId = null) {
  const id = jobId || currentJobId;
  if (!id) return;
  try {
    const res = await fetch(`/api/jobs/${id}/result`);
    const data = await res.json();
    if (!data.ok) {
      throw new Error(data.error?.message || 'نتیجه آماده نیست');
    }
    currentResult = data.result;
    currentJobId = id;
    showClean = true;
    updateResultView();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function loadHistory() {
  try {
    const res = await fetch('/api/history?limit=10');
    const data = await res.json();
    if (!data.ok) throw new Error(data.error?.message || 'خطا در تاریخچه');
    historyList.innerHTML = '';
    data.jobs.forEach(job => {
      const li = document.createElement('li');
      li.className = 'p-3 border rounded cursor-pointer hover:bg-gray-50';
      li.innerHTML = `<div class="flex justify-between"><span class="font-medium">${job.original_filename}</span><span class="text-xs text-gray-500">${new Date(job.created_at).toLocaleString('fa-IR')}</span></div><div class="text-xs text-gray-600">وضعیت: ${job.status}</div>`;
      li.addEventListener('click', async () => {
        currentJobId = job.id;
        setStatus(job.status, job.progress);
        if (job.status === 'done') {
          await loadResult(job.id);
        } else {
          startPolling();
        }
      });
      historyList.appendChild(li);
    });
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function handleFiles(files) {
  if (!files.length) return;
  uploadFile(files[0]);
}

selectFileBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

['dragenter', 'dragover'].forEach(evt => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.add('border-indigo-400', 'bg-indigo-50');
  });
});
['dragleave', 'drop'].forEach(evt => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove('border-indigo-400', 'bg-indigo-50');
  });
});
dropZone.addEventListener('drop', (e) => {
  const dt = e.dataTransfer;
  if (dt?.files?.length) {
    handleFiles(dt.files);
  }
});

copyBtn.addEventListener('click', async () => {
  if (!resultText.value) return;
  await navigator.clipboard.writeText(resultText.value);
  showToast('کپی شد', 'success');
});

downloadBtn.addEventListener('click', async () => {
  if (!currentJobId) return;
  const res = await fetch(`/api/jobs/${currentJobId}/download`);
  if (!res.ok) {
    showToast('فایل آماده نیست', 'error');
    return;
  }
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `result_${currentJobId}.txt`;
  a.click();
  window.URL.revokeObjectURL(url);
});

toggleClean.addEventListener('click', () => {
  showClean = true;
  updateResultView();
});

toggleRaw.addEventListener('click', () => {
  showClean = false;
  updateResultView();
});

refreshHistoryBtn.addEventListener('click', loadHistory);

loadHistory();
