const form = document.getElementById("processForm");
const processBtn = document.getElementById("processBtn");
const clearBtn = document.getElementById("clearBtn");
const newRunBtn = document.getElementById("newRunBtn");

const statusEl = document.getElementById("status");
const messagesEl = document.getElementById("messages");
const workbookEl = document.getElementById("workbook");
const updateExistingEl = document.getElementById("updateExisting");

const resultEmpty = document.getElementById("resultEmpty");
const resultWrap = document.getElementById("result");

const downloadBtn = document.getElementById("downloadBtn");
const expiryNote = document.getElementById("expiryNote");

const rParsed = document.getElementById("rParsed");
const rInserted = document.getElementById("rInserted");
const rDuplicates = document.getElementById("rDuplicates");
const rAmount = document.getElementById("rAmount");
const rFees = document.getElementById("rFees");

const healthPill = document.getElementById("healthPill");

function setStatus(type, text) {
  statusEl.className = "status " + type;
  statusEl.textContent = text;
  statusEl.style.display = "block";
}

function resetStatus() {
  statusEl.style.display = "none";
  statusEl.textContent = "";
  statusEl.className = "status info";
}

function formatKES(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return "KSh 0.00";
  return "KSh " + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function setLoading(isLoading) {
  if (isLoading) {
    processBtn.classList.add("loading");
    processBtn.disabled = true;
    clearBtn.disabled = true;
    healthPill.textContent = "Status: Processing";
  } else {
    processBtn.classList.remove("loading");
    processBtn.disabled = false;
    clearBtn.disabled = false;
    healthPill.textContent = "Status: Ready";
  }
}

function showResult(data) {
  resultEmpty.style.display = "none";
  resultWrap.style.display = "block";

  rParsed.textContent = data.parsed;
  rInserted.textContent = data.inserted;
  rDuplicates.textContent = data.duplicates;
  rAmount.textContent = formatKES(data.total_amount);
  rFees.textContent = formatKES(data.total_fees);

  downloadBtn.href = "/download/" + data.download_token;

  const minutes = Math.round((data.ttl_seconds || 1800) / 60);
  expiryNote.textContent = "Download link expires in about " + minutes + " minutes.";
}

function resetUIForNewRun() {
  resetStatus();
  resultWrap.style.display = "none";
  resultEmpty.style.display = "block";
  downloadBtn.href = "#";
  expiryNote.textContent = "";
  healthPill.textContent = "Status: Ready";
}

clearBtn.addEventListener("click", () => {
  messagesEl.value = "";
  workbookEl.value = "";
  resetUIForNewRun();
});

newRunBtn.addEventListener("click", () => {
  resetUIForNewRun();
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  resetStatus();

  if (!messagesEl.value.trim()) {
    setStatus("error", "Please paste at least one message.");
    return;
  }
  if (!workbookEl.files || workbookEl.files.length === 0) {
    setStatus("error", "Please upload the Expenditure Tracker .xlsx file.");
    return;
  }

  const fd = new FormData();
  fd.append("messages", messagesEl.value);
  fd.append("workbook", workbookEl.files[0]);
  if (updateExistingEl.checked) fd.append("update_existing", "1");

  setLoading(true);
  setStatus("info", "Processing messages and preparing updated workbook...");

  try {
    const resp = await fetch("/api/process", { method: "POST", body: fd });
    const data = await resp.json();

    if (!resp.ok || !data.ok) {
      setStatus("error", data.error || "Processing failed.");
      setLoading(false);
      return;
    }

    setStatus("success", "Processing complete. Download is available when you choose.");
    showResult(data);
    setLoading(false);
  } catch (err) {
    setStatus("error", "Network or server error while processing.");
    setLoading(false);
  }
});

// Lightweight health check
fetch("/health")
  .then(r => r.json())
  .then(() => { healthPill.textContent = "Status: Ready"; })
  .catch(() => { healthPill.textContent = "Status: Offline"; });