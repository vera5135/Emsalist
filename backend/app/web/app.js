const $ = (id) => document.getElementById(id);

const FILE_API_BASES = ["http://127.0.0.1:8003", "http://127.0.0.1:8001", "http://127.0.0.1:8000"];
let activeApiBase = window.location.protocol === "file:" ? FILE_API_BASES[0] : "";
const apiUrl = (path) => `${activeApiBase}${path}`;

const els = {
  healthPill: $("healthPill"),
  caseText: $("caseText"),
  practiceArea: $("practiceArea"),
  maxResults: $("maxResults"),
  requestType: $("requestType"),
  strategyOutput: $("strategyOutput"),
  questionFields: $("questionFields"),
  statusLine: $("statusLine"),
  themeToggle: $("themeToggle"),
  analysisOutput: $("analysisOutput"),
  brainOutput: $("brainOutput"),
  decisionOutput: $("decisionOutput"),
  draftOutput: $("draftOutput"),
  petitionReadinessNotice: $("petitionReadinessNotice"),
  riskOutput: $("riskOutput"),
  strategyTabOutput: $("strategyTabOutput"),
  clientQuestionsOutput: $("clientQuestionsOutput"),
  defenseOutput: $("defenseOutput"),
  officialSourcesOutput: $("officialSourcesOutput"),
  documentFiles: $("documentFiles"),
  documentType: $("documentType"),
  documentApproval: $("documentApproval"),
  documentOutput: $("documentOutput"),
  documentCount: $("documentCount"),
  documentGroundingState: $("documentGroundingState"),
  documentSelectionState: $("documentSelectionState"),
  evidenceOutput: $("evidenceOutput"),
  evidenceCount: $("evidenceCount"),
  draftReadinessDialog: $("draftReadinessDialog"),
  draftReadinessIssues: $("draftReadinessIssues"),
  analysisCount: $("analysisCount"),
  brainCount: $("brainCount"),
  decisionCount: $("decisionCount"),
  riskCount: $("riskCount"),
  strategyCount: $("strategyCount"),
  defenseCount: $("defenseCount"),
  officialSourceCount: $("officialSourceCount"),
  buttons: [
    $("reviewBtn"),
    $("aiEnrichBtn"),
    $("aiQuestionsBtn"),
    $("aiSearchBtn"),
    $("analyzeBtn"),
    $("brainBtn"),
    $("auditSourcesBtn"),
    $("yargitayBtn"),
    $("auditPrecedentsBtn"),
    $("draftBtn"),
    $("finalPetitionBtn"),
    $("auditDraftBtn"),
    $("refineDraftBtn"),
    $("sampleBtn"),
    $("questionsBtn"),
    $("clearBtn"),
    $("copyDraftBtn"),
    $("printDraftBtn"),
    $("downloadDraftBtn"),
    $("downloadDocxBtn"),
    $("downloadPdfBtn"),
    $("downloadUdfBtn"),
    $("copyClientQuestionsBtn"),
    $("uploadDocumentsBtn"),
    $("analyzeDocumentsBtn"),
    $("confirmPreliminaryDraftBtn"),
  ].filter(Boolean),
};

let lastDecisions = [];
let lastBrainResults = [];
let lastCaseEnrichment = null;
let lastBetterSearches = null;
let lastStrategy = null;
let lastStrategyCase = "";
let lastStrategyRequest = "";
let questionFlow = {
  questions: [],
  currentIndex: 0,
  answers: {},
  skipped: new Set(),
  showAll: false,
};
let lastDraftData = null;
let lastDraftAudit = null;
let lastSourceAudit = null;
let lastPrecedentAudit = null;
let lastYargitaySearch = null;
let lastDocuments = [];
let lastDocumentAnalysis = null;
/** @type {File[]} Gerçek File objelerini saklar, plain object değil. */
let selectedDocumentFiles = [];
let uiBusy = false;
let reviewWorkflowComplete = false;
let pendingPreliminaryDraftOptions = null;

const DOCUMENT_FACT_LABELS = {
  court: "Mahkeme",
  case_number: "Dosya numarası",
  parties: "Taraflar",
  document_date: "Belge tarihi",
  service_date: "Tebliğ tarihi",
  hearing_date: "Duruşma tarihi",
  deadlines: "Süre",
  sale_date: "Satış tarihi",
  sale_price: "Satış bedeli",
  vehicle_make_model: "Araç marka/model",
  vehicle_plate: "Plaka",
  vehicle_vin: "Şasi",
  notary_info: "Noterlik",
  notice_date: "İhtar tarihi",
  claim_result: "Talep sonucu",
  evidence: "Deliller",
  report_date: "Rapor tarihi",
  report_number: "Rapor numarası",
  technical_findings: "Teknik tespit",
  payment_info: "Ödeme/dekont",
  power_of_attorney_info: "Vekalet",
  risk_signals: "Risk sinyali",
};

const sampleCase = `Müvekkil, maliki olduğu konutu davalı kiracıya yazılı kira sözleşmesi ile kiraya vermiştir. Müvekkilin evlenen oğlu ve gelini için bağımsız konuta ihtiyaç doğmuştur. Müvekkilin aynı ilçe sınırlarında oturmaya elverişli başka bir konutu bulunmamaktadır. Kiracıya durum sözlü olarak bildirilmiş, ancak kiracı taşınmayı kabul etmemiştir. Kira sözleşmesi dönem sonunda sona ermiş olmasına rağmen kiracı taşınmazı kullanmaya devam etmektedir. Müvekkilin ve ailesinin gerçek, samimi ve zorunlu konut ihtiyacı bulunduğundan ihtiyaç nedeniyle tahliye davası açılması istenmektedir.`;
const THEME_STORAGE_KEY = "emsalist-theme";
const UNRELATED_ARGUMENT = "Bu kaynak somut uyuşmazlıkla doğrudan bağlantılı görünmemektedir.";
const DEFAULT_PRECEDENT_PARAGRAPH =
  "Karar, gizli ayıp, ayıp ihbarı ve seçimlik hakların değerlendirilmesi bakımından somut uyuşmazlıkla bağlantılıdır.";
const RISK_PRECEDENT_PARAGRAPH =
  "Bu karar doğrudan lehe emsal gibi sunulmamalı; davalı savunması ve somut olayın ayrılan yönleri bakımından değerlendirilmelidir.";
const CLEAN_PRECEDENT_EXPLANATION =
  "Anılan kararda, ayıplı satışta ayıbın niteliği, alıcının seçimlik hakları ve delil değerlendirmesi yönünden ilkeler ortaya konulmuştur. Bu karar, somut olayda gizli ayıp iddiası ve seçimlik hakların kullanılması bakımından emsal olarak değerlendirilebilir.";

const defectiveVehicleRequest =
  "Öncelikle sözleşmeden dönülerek satış bedelinin iadesi, aksi halde ayıp oranında bedel indirimi ve zarar kalemlerinin tahsili";

const fallbackQuestions = [
  "Tarafların sıfatı ve uyuşmazlıktaki rolleri nelerdir?",
  "Somut talep ve dava türü nedir?",
  "Talebi destekleyen belge, kayıt, tanık veya diğer deliller nelerdir?",
  "Karşı tarafın muhtemel savunması veya riskli nokta nedir?",
];

const commonAnswerOptions = ["Belge mevcut", "Bilmiyorum", "Sonra tamamlanacak"];

const vehicleQuestionBank = [
  {
    question: "Satıcı kim?",
    options: ["Galeri/şirket", "Gerçek kişi", "Tacir", "Bilmiyorum"],
    requiredTerms: ["satici", "galeri", "sirket", "tacir"],
  },
  {
    question: "Satış belgesi ve ödeme bilgisi nedir?",
    options: ["Noter satış sözleşmesi var", "Banka dekontu var", "Elden ödeme", "Belge yok"],
    requiredTerms: ["noter", "satis belgesi", "dekont", "odeme", "bedel"],
  },
  {
    question: "Araç bilgisi ve satış bedeli belli mi?",
    options: ["Plaka/şasi bilgisi belli", "Satış bedeli belli", "Marka-model belli", "Eksik"],
    requiredTerms: ["plaka", "sasi", "marka", "model", "bedel"],
  },
  {
    question: "Satıcı satış öncesinde nasıl beyanda bulundu?",
    options: ["Sorunsuz denildi", "Kazasız denildi", "Ağır hasarsız denildi", "İlan görüntüsü var"],
    requiredTerms: ["beyan", "sorunsuz", "kazasiz", "hasarsiz", "ilan"],
  },
  {
    question: "Arıza veya ayıp nasıl tespit edildi?",
    options: ["Servis raporu", "Ekspertiz raporu", "TRAMER kaydı", "Henüz belge yok"],
    requiredTerms: ["servis", "ekspertiz", "tramer", "rapor", "ariza"],
  },
  {
    question: "Ayıp ne zaman ortaya çıktı?",
    options: ["Teslimden kısa süre sonra", "İlk kullanımda", "Serviste öğrenildi", "Tarih belirsiz"],
    requiredTerms: ["teslim", "kisa sure", "tarih", "ortaya cikti"],
  },
  {
    question: "Satıcıya ne zaman ve nasıl bildirim yapıldı?",
    options: ["WhatsApp/SMS", "Noter ihtarı", "Telefonla bildirildi", "Henüz bildirilmedi"],
    requiredTerms: ["bildirim", "ihbar", "ihtar", "whatsapp", "sms"],
  },
  {
    question: "Talep ve masraf kalemleri nelerdir?",
    options: ["Bedel iadesi", "Bedel indirimi", "Onarım gideri", "Ekspertiz/servis masrafı"],
    requiredTerms: ["bedel iadesi", "bedel indirimi", "onarim", "masraf", "talep"],
  },
];

const optionSets = {
  eviction: [
    [["adres", "sozlesme", "sözleşme", "baslangic", "başlangıç"], ["Yazılı kira sözleşmesi var", "Başlangıç tarihi sözleşmede", "Tapu kaydı mevcut", "Adres resmi kayıtla teyitli"]],
    [["kimin", "kim için"], ["Müvekkilin kendisi", "Müvekkilin oğlu/kızı", "Yeni evli aile bireyi", "İşyeri ihtiyacı"]],
    [["gercek", "gerçek", "samimi", "zorunlu"], ["Bağımsız konut ihtiyacı", "Mevcut konut yetersiz", "Aynı bölgede uygun taşınmaz yok", "İhtiyaç sürekli"]],
    [["baska", "başka", "uygun", "tasinmaz", "taşınmaz"], ["Başka uygun taşınmaz yok", "Var ancak ihtiyaca elverişli değil", "Taşınmaz dolu/kiracı var", "Tapu kayıtları istenecek"]],
    [["ihtar", "bildirim"], ["İhtarname gönderildi", "Sözlü bildirim yapıldı", "Tebliğ tarihi var", "Henüz ihtar yok"]],
    [["sure", "süre", "tarih"], ["Dönem sonu takip edildi", "Dava süresi içinde", "Tarih kontrol edilecek", "Tebliğ tarihi belli"]],
    [["delil", "belge", "tanik", "tanık"], ["Kira sözleşmesi", "Tapu kaydı", "İhtarname", "Nüfus kaydı", "Tanık"]],
  ],
  alimony: [
    [["gelir", "gider"], ["Emekli maaşı", "Kira gideri", "Sağlık gideri", "Düzenli borç ödemesi"]],
    [["nafaka", "miktar"], ["Aylık nafaka düzenli ödeniyor", "Ödeme dekontları var", "Karar tarihi belli", "Miktar güncel değil"]],
    [["alacakli", "alacaklı", "calistigina", "çalıştığına"], ["SGK kaydı istenecek", "Sosyal medya çıktısı", "Tanık", "Banka/tapu/araç kaydı"]],
    [["sosyal", "ekonomik", "degisiklik", "değişiklik"], ["Davalının geliri arttı", "Müvekkilin geliri azaldı", "Yeni aile yükümlülüğü", "Hakkaniyet değişti"]],
    [["talep"], ["Öncelikle kaldırma", "Aksi halde indirim", "Sosyal-ekonomik araştırma", "Tedbiren değerlendirme"]],
  ],
  labor: [
    [["giris", "giriş", "cikis", "çıkış", "tarih"], ["SGK hizmet dökümü var", "İşe giriş tarihi belli", "İşten çıkış tarihi belli", "Tanıkla desteklenecek"]],
    [["ucret", "ücret", "gorev", "görev"], ["Banka + elden ödeme", "Bordro gerçeği yansıtmıyor", "Emsal ücret araştırması", "Fiili görev farklı"]],
    [["fesih"], ["Haksız fesih", "Yazılı fesih bildirimi yok", "İşveren feshi", "Haklı nedenle işçi feshi"]],
    [["alacak"], ["Kıdem", "İhbar", "Fazla mesai", "Yıllık izin", "UBGT"]],
    [["fazla", "tatil", "bayram"], ["Tanık", "Puantaj", "Vardiya kayıtları", "Giriş-çıkış kayıtları"]],
    [["arabuluculuk"], ["Anlaşamama tutanağı var", "Tutanak tarihi belli", "Tüm alacak kalemleri yazıldı", "Tutanak kontrol edilecek"]],
  ],
  enforcement: [
    [["dosya", "takip", "tarih", "miktar"], ["İcra dosya no belli", "Takip tarihi belli", "Ödeme emri tebliğ edildi", "Takip miktarı belli"]],
    [["dayanak", "sozlesme", "sözleşme", "fatura", "senet"], ["Sözleşme", "Fatura", "Cari hesap", "E-posta yazışmaları", "Banka dekontu"]],
    [["itiraz", "gerekce", "gerekçe"], ["Borca itiraz", "Yetkiye itiraz", "İmzaya itiraz", "Gerekçesiz itiraz"]],
    [["likit"], ["Alacak likit", "Fatura/sözleşme ile belirli", "Bilirkişi gerekebilir", "Ticari defter kaydı var"]],
    [["inkar", "tazminat"], ["İcra inkar tazminatı talep edilecek", "En az %20", "Likit alacak vurgulanacak", "Şimdilik talep yok"]],
    [["risk", "yetki", "zamana"], ["Yetki riski var", "Zamanaşımı kontrol edilecek", "Tebligat kontrol edilecek", "Arabuluculuk gerekmez"]],
  ],
  defectiveVehicle: [
    [["satici", "satıcı", "galeri", "tacir", "tuketici", "tüketici"], ["Galeri/şirket satıcı", "Gerçek kişi satıcı", "Tüketici işlemi olabilir", "Görevli mahkeme kontrol edilecek"]],
    [["marka", "model", "plaka", "sasi", "şasi", "bedel", "satis", "satış"], ["Noter satış sözleşmesi var", "Satış bedeli ödendi", "Plaka/şasi bilgisi belli", "Ödeme dekontu mevcut"]],
    [["beyan", "ekspertiz", "ilan"], ["Kazasız beyan edildi", "Ağır hasarsız beyan edildi", "Ekspertiz raporu var", "İlan görüntüsü mevcut", "Mesaj yazışmaları var"]],
    [["agir", "ağır", "kilometre", "motor", "mekanik", "onarim", "onarım", "tespit"], ["Ağır hasar kaydı çıktı", "Motor arızası tespit edildi", "Gizli onarım izi var", "Kilometre şüphesi var", "Servis raporu mevcut"]],
    [["olagan", "olağan", "gizli"], ["Olağan muayene ile anlaşılamaz", "Gizli ayıp niteliğinde", "Teslimden kısa süre sonra ortaya çıktı", "Bilirkişi ile tespit edilmeli"]],
    [["bildirim", "ihbar"], ["Ayıp öğrenilince bildirildi", "WhatsApp/SMS ile bildirildi", "Noter ihtarı gönderildi", "Bildirim tarihi belli"]],
    [["secimlik", "seçimlik", "donme", "dönme", "bedel", "onarim", "onarım"], ["Öncelikle sözleşmeden dönme", "Aksi halde bedel indirimi", "Onarım gideri talebi", "Satış bedeli iadesi"]],
    [["zarar", "masraf", "deger", "değer"], ["Satış bedeli ile ayıplı değer farkı var", "Servis/onarım gideri var", "Ekspertiz masrafı var", "Değer kaybı bilirkişiyle belirlensin"]],
    [["delil", "servis", "hasar", "rapor", "yazisma", "yazışma", "tanik", "tanık"], ["Servis raporu", "Ekspertiz raporu", "TRAMER/hasar kaydı", "İlan ve yazışmalar", "Tanık"]],
  ],
  generic: [
    [["taraf", "rol"], ["Davacı alacaklı", "Davacı kiraya veren", "Davacı işçi", "Davalı borçlu"]],
    [["talep", "dava"], ["Asıl talep", "Terditli talep", "Tedbir talebi", "Yargılama gideri"]],
    [["delil", "belge", "kayıt", "tanik", "tanık"], ["Belge var", "Tanık var", "Resmi kayıt istenecek", "Bilirkişi gerekir"]],
    [["savunma", "risk"], ["Zamanaşımı savunması", "Yetki/görev itirazı", "İspat riski", "Karşı delil bekleniyor"]],
  ],
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function plainText(value) {
  return String(value ?? "")
    .toLocaleLowerCase("tr-TR")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replaceAll("ı", "i")
    .replaceAll("ı", "i")
    .replaceAll("ğ", "g")
    .replaceAll("ü", "u")
    .replaceAll("ş", "s")
    .replaceAll("ö", "o")
    .replaceAll("ç", "c")
    .replaceAll("ı", "i")
    .replaceAll("ğ", "g")
    .replaceAll("ü", "u")
    .replaceAll("Ş", "s")
    .replaceAll("Ö", "o")
    .replaceAll("Ç", "c")
    .replaceAll("İ", "i")
    .replaceAll("Ğ", "g")
    .replaceAll("Ü", "u");
}

function currentProfileKey() {
  const text = plainText(`${lastStrategy?.petition_type || ""} ${getRequestType()} ${getCaseText()}`);
  if (text.includes("tahliye") || text.includes("kiralanan") || text.includes("kiraci")) return "eviction";
  if (text.includes("nafaka")) return "alimony";
  if (text.includes("iscilik") || text.includes("kidem") || text.includes("ihbar") || text.includes("fazla mesai")) return "labor";
  if (text.includes("icra") || text.includes("itiraz") || text.includes("takip")) return "enforcement";
  if (text.includes("ayip") || text.includes("arac") || text.includes("ekspertiz") || text.includes("tramer")) return "defectiveVehicle";
  return "generic";
}

function questionOptions(question) {
  const normalizedQuestion = plainText(question);
  if (currentProfileKey() === "defectiveVehicle") {
    const direct = vehicleQuestionBank.find((item) => plainText(item.question) === normalizedQuestion);
    if (direct) return direct.options.slice(0, 5);
    const matchedVehicle = vehicleQuestionBank.find((item) =>
      item.requiredTerms.some((term) => normalizedQuestion.includes(term) || plainText(item.question).includes(normalizedQuestion)),
    );
    if (matchedVehicle) return matchedVehicle.options.slice(0, 5);
  }
  const profileKey = currentProfileKey();
  const profileOptions = optionSets[profileKey] || [];
  const matched = [];

  for (const [needles, options] of profileOptions) {
    if (needles.some((needle) => normalizedQuestion.includes(plainText(needle)))) {
      matched.push(...options);
    }
  }

  if (!matched.length) matched.push(...commonAnswerOptions);
  return [...new Set(matched)].slice(0, 5);
}

function appendAnswerOption(field, value) {
  const current = field.value.trim();
  if (!current) {
    field.value = value;
  } else if (!current.split(";").map((item) => item.trim()).includes(value)) {
    field.value = `${current}; ${value}`;
  }
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

function setFieldValue(field, value) {
  field.value = value;
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

function setBusy(isBusy, message) {
  uiBusy = isBusy;
  els.buttons.forEach((button) => {
    button.disabled = isBusy;
  });
  renderDocumentControls();
  if (message !== undefined) {
    setStatus(message);
  }
}

function setStatus(message, isError = false) {
  els.statusLine.textContent = message;
  els.statusLine.classList.toggle("error", isError);
}

function applyTheme(theme) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = nextTheme;
  if (els.themeToggle) {
    els.themeToggle.checked = nextTheme === "dark";
  }
  localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
}

function initTheme() {
  const storedTheme = localStorage.getItem(THEME_STORAGE_KEY);
  applyTheme(storedTheme === "dark" ? "dark" : "light");
}

function switchTab(tabName) {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabName);
  });
  document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.tabPanel === tabName);
  });
}

function cleanOutputText(value, fallback = "") {
  const text = String(value ?? "").replaceAll("{paragraph}", "").replaceAll("{{paragraph}}", "").trim();
  return text || fallback;
}

function renderListItems(values, fallback = "") {
  const items = (Array.isArray(values) ? values : [])
    .map((value) => String(value ?? "").trim())
    .filter(Boolean)
    .map((value) => `<li>${escapeHtml(value)}</li>`);
  if (items.length) {
    return `<ul class="compact-list">${items.join("")}</ul>`;
  }
  return fallback ? `<span>${escapeHtml(fallback)}</span>` : "";
}

function getCaseText() {
  return els.caseText.value.trim();
}

function getRequestType() {
  return els.requestType.value.trim() || "Talebimizin kabulü";
}

function requestIsGeneric() {
  const value = plainText(els.requestType.value);
  return !value || value === "talebimizin kabulu";
}

function applyProfileRequestDefault(strategy) {
  const profileText = plainText([strategy?.petition_type, ...(strategy?.legal_basis || [])].join(" "));
  const looksLikeDefectiveVehicle =
    profileText.includes("ayipli arac") ||
    profileText.includes("gizli ayip") ||
    profileText.includes("tbk 219") ||
    currentProfileKey() === "defectiveVehicle";
  if (looksLikeDefectiveVehicle && requestIsGeneric()) {
    setFieldValue(els.requestType, defectiveVehicleRequest);
  }
}

function getMaxResults() {
  const value = Number.parseInt(els.maxResults.value, 10);
  return Number.isFinite(value) ? Math.min(Math.max(value, 1), 20) : 5;
}

function getPracticeArea() {
  return els.practiceArea.value.trim() || null;
}

function assertCaseText() {
  const caseText = getCaseText();
  if (caseText.length < 10) {
    throw new Error("Olay veya hukuki konu en az 10 karakter olmalı.");
  }
  return caseText;
}

async function apiFetch(path, options = {}) {
  if (window.location.protocol !== "file:") {
    return fetch(path, options);
  }

  const bases = [...new Set([activeApiBase, ...FILE_API_BASES].filter(Boolean))];
  let lastError = null;
  for (const base of bases) {
    try {
      const response = await fetch(`${base}${path}`, options);
      activeApiBase = base;
      updateApiLinks();
      return response;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("API bağlantısı kurulamadı.");
}

async function apiPost(path, payload) {
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg || JSON.stringify(item)).join("; ")
      : data.detail || response.statusText;
    throw new Error(detail);
  }
  return data;
}

async function apiUpload(path, formData) {
  const response = await apiFetch(path, { method: "POST", body: formData });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg || JSON.stringify(item)).join("; ")
      : data.detail || response.statusText;
    throw new Error(detail);
  }
  return data;
}

function renderDocumentControls() {
  if (!els.documentFiles) return;
  $("uploadDocumentsBtn").disabled = uiBusy || selectedDocumentFiles.length === 0;
  $("analyzeDocumentsBtn").disabled = uiBusy || lastDocuments.length === 0;
  updateFinalPetitionReadiness();
}

function finalPetitionReadinessIssues() {
  const issues = [];
  if (!lastDocuments.length) issues.push("Belge yüklenmedi.");
  else if (!lastDocumentAnalysis) issues.push("Belge analizi tamamlanmadı.");
  if (lastDocumentAnalysis && !els.documentApproval.checked) issues.push("Belge analizi ve kaynak/risk incelemesi onaylanmadı.");
  if (!reviewWorkflowComplete) issues.push("Kaynaklar, deliller, emsaller ve risk incelemesi tamamlanmadı.");
  if (questionAnswerCount() === 0) issues.push("Dilekçe soruları cevaplanmadı.");
  return issues;
}

function updateFinalPetitionReadiness() {
  if (!els.petitionReadinessNotice) return;
  const issues = finalPetitionReadinessIssues();
  const ready = issues.length === 0;
  els.petitionReadinessNotice.className = `petition-readiness ${ready ? "ready" : "warning"}`;
  els.petitionReadinessNotice.textContent = ready
    ? "Analiz ve onaylar tamamlandı. Nihai dilekçe taslağını hazırlayabilirsiniz."
    : "Dilekçe taslağı için önce belge analizi, kaynaklar, deliller ve riskler incelenip onaylanmalıdır.";
}

function renderDocumentSelection() {
  const names = selectedDocumentFiles.map((file) => {
    if (file instanceof File) {
      return `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    }
    return String(file.name || file);
  });
  els.documentSelectionState.className = `document-selection-state${names.length ? " pending" : ""}`;
  els.documentSelectionState.textContent = names.length
    ? `${names.length} dosya seçildi, yükleme bekliyor: ${names.join(", ")}`
    : "Yükleme için dosya seçilmedi.";
  renderDocumentControls();
}

function renderDocumentEvidence() {
  const documents = lastDocumentAnalysis?.documents || [];
  const evidenceFacts = documents.flatMap((documentItem) =>
    (documentItem.extracted_facts || []).filter((fact) => fact.verification_status === "fact_confirmed"),
  );
  els.evidenceCount.textContent = String(evidenceFacts.length);
  if (!documents.length) {
    els.evidenceOutput.className = "empty-state";
    els.evidenceOutput.textContent = "Henüz analiz edilmiş belge delili yok.";
    return;
  }
  els.evidenceOutput.className = "result-list";
  els.evidenceOutput.innerHTML = documents
    .map((documentItem) => {
      const facts = (documentItem.extracted_facts || []).filter((fact) => fact.verification_status === "fact_confirmed");
      return `
        <div class="result-item">
          <h3>${escapeHtml(documentItem.file_name)}</h3>
          <div class="meta-row">
            <span class="chip">${escapeHtml(documentItem.document_type)}</span>
            <span class="chip status-${escapeHtml(documentItem.extraction_status)}">${escapeHtml(documentItem.extraction_status)}</span>
          </div>
          ${facts.length ? `<ol class="compact-list">${facts.map((fact) => `
            <li><strong>${escapeHtml(DOCUMENT_FACT_LABELS[fact.fact_key] || fact.fact_key)}:</strong> ${escapeHtml(fact.fact_value)}<br>
            <small>Kaynak: ${escapeHtml(fact.source_file_name)}${fact.page_number ? `, s. ${escapeHtml(fact.page_number)}` : ""}; alıntı: “${escapeHtml(fact.excerpt)}”</small></li>
          `).join("")}</ol>` : "<p>Bu belgeden doğrulanmış metinsel delil çıkarılamadı.</p>"}
        </div>
      `;
    })
    .join("");
}

function renderDocuments() {
  els.documentCount.textContent = `${lastDocuments.length} belge`;
  if (!lastDocuments.length) {
    els.documentOutput.className = "document-list empty-state";
    els.documentOutput.textContent = "Henüz dosya evrakı eklenmedi.";
    els.documentGroundingState.className = "document-grounding-state";
    els.documentGroundingState.textContent = "Dilekçe için henüz analiz edilmiş belge yok.";
    renderDocumentEvidence();
    renderDocumentControls();
    return;
  }

  els.documentOutput.className = "document-list";
  els.documentOutput.innerHTML = lastDocuments
    .map((documentItem) => {
      const status = String(documentItem.extraction_status || "failed");
      const statusClass = ["extracted", "partial", "ocr_required", "conversion_required", "unsupported", "failed"].includes(status)
        ? `status-${status}`
        : "status-failed";
      const facts = (documentItem.extracted_facts || []).slice(0, 10);
      const missing = documentItem.missing_fields || [];
      const conflicts = documentItem.conflicts || [];
      return `
        <article class="document-card">
          <div class="document-card-head">
            <div>
              <h3>${escapeHtml(documentItem.file_name)}</h3>
              <div class="meta-row">
                <span class="chip">${escapeHtml(documentItem.document_type || "diğer")}</span>
                <span class="chip ${statusClass}">${escapeHtml(status)}</span>
                <span class="chip">${escapeHtml(documentItem.file_extension || "")}</span>
              </div>
            </div>
            <button class="ghost-btn small-btn" type="button" data-delete-document="${escapeHtml(documentItem.document_id)}">Sil</button>
          </div>
          ${documentItem.extraction_warning ? `<p class="document-warning"><strong>Uyarı:</strong> ${escapeHtml(documentItem.extraction_warning)}</p>` : ""}
          ${facts.length ? `
            <ol class="document-facts">
              ${facts.map((fact) => `
                <li>
                  <strong>${escapeHtml(DOCUMENT_FACT_LABELS[fact.fact_key] || fact.fact_key)}:</strong>
                  ${escapeHtml(fact.fact_value)}
                  <small>Kaynak: ${escapeHtml(fact.source_file_name)}${fact.page_number ? `, s. ${escapeHtml(fact.page_number)}` : ""}; güven ${Math.round(Number(fact.confidence_score || 0) * 100)}% — “${escapeHtml(fact.excerpt || "")}”</small>
                </li>
              `).join("")}
            </ol>
          ` : ""}
          ${missing.length ? `<p><strong>Eksikler:</strong> ${escapeHtml(missing.map((key) => DOCUMENT_FACT_LABELS[key] || key).join(", "))}</p>` : ""}
          ${conflicts.map((conflict) => `<p class="document-conflict"><strong>Çelişki:</strong> ${escapeHtml(conflict.warning)}</p>`).join("")}
        </article>
      `;
    })
    .join("");

  if (!lastDocumentAnalysis) {
    els.documentGroundingState.className = "document-grounding-state warning";
    els.documentGroundingState.textContent = "Belgeler yüklendi. Dilekçe akışından önce Belgeleri Analiz Et adımını çalıştırın.";
    renderDocumentEvidence();
    renderDocumentControls();
    return;
  }
  const conflictCount = (lastDocumentAnalysis.conflicts || []).length;
  const warningCount = (lastDocumentAnalysis.warnings || []).length;
  els.documentGroundingState.className = `document-grounding-state ${lastDocumentAnalysis.grounding_ready ? "ready" : "warning"}`;
  els.documentGroundingState.textContent = lastDocumentAnalysis.grounding_ready
    ? `${(lastDocumentAnalysis.confirmed_facts || []).length} bilgi kaynaklandırıldı; dilekçe akışı için analizi onaylayın.`
    : `Analiz tamamlandı: ${conflictCount} çelişki, ${warningCount} okuma/OCR uyarısı. Kesin bilgi olarak yalnızca doğrulanan olgular kullanılacak.`;
  renderDocumentEvidence();
  renderDocumentControls();
}

function userClaimsFromCase() {
  const text = `${getCaseText()} ${getRequestType()}`;
  const patterns = {
    sale_price: /satış\s+bedel(?:i)?\s*[:\-]?(?:nin)?\s*((?:\d{1,3}(?:[. ]\d{3})+|\d+)(?:,\d{1,2})?\s*(?:TL|TRY|₺))/i,
    sale_date: /satış\s+tarih(?:i)?\s*[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{4})/i,
    vehicle_plate: /plaka(?:\s+numarası)?\s*[:\-]?\s*(\d{2}\s*[A-ZÇĞİÖŞÜ]{1,3}\s*\d{2,5})/i,
    vehicle_vin: /(?:şasi|şase|VIN)(?:\s+numarası)?\s*[:\-]?\s*([A-HJ-NPR-Z0-9]{17})/i,
    case_number: /(?:esas|dosya)\s*(?:no|numarası)?\s*[:\-]?\s*(\d{4}\s*\/\s*\d+)/i,
  };
  return Object.fromEntries(
    Object.entries(patterns)
      .map(([key, pattern]) => [key, text.match(pattern)?.[1]?.trim()])
      .filter(([, value]) => value),
  );
}

function documentFactPayload() {
  return (lastDocumentAnalysis?.confirmed_facts || []).filter((fact) => fact.verification_status === "fact_confirmed");
}

function documentConfirmedFactTexts() {
  return documentFactPayload().map((fact) => {
    const label = DOCUMENT_FACT_LABELS[fact.fact_key] || fact.fact_key;
    const page = fact.page_number ? `, s. ${fact.page_number}` : "";
    return `${label}: ${fact.fact_value} (Kaynak belge: ${fact.source_file_name}${page}; alıntı: ${fact.excerpt})`;
  });
}

function documentMissingFields() {
  return (lastDocumentAnalysis?.missing_fields || []).map((key) => DOCUMENT_FACT_LABELS[key] || key);
}

function documentMissingQuestions() {
  return documentMissingFields().map((label) => `Belgeden çıkarılamayan ${label} bilgisi nedir?`);
}

function prefillQuestionsFromDocuments() {
  const facts = documentFactPayload();
  if (!facts.length || !questionFlow.questions.length) return;
  const termsByFact = {
    parties: ["taraf", "satıcı", "alıcı"],
    sale_price: ["satış bedeli", "bedel"],
    sale_date: ["satış tarihi"],
    vehicle_make_model: ["marka", "model", "araç bilgisi"],
    vehicle_plate: ["plaka"],
    vehicle_vin: ["şasi", "şase"],
    evidence: ["delil"],
    claim_result: ["talep"],
    service_date: ["tebliğ"],
    hearing_date: ["duruşma"],
    payment_info: ["ödeme", "dekont"],
    technical_findings: ["arıza", "tespit", "rapor"],
  };
  questionFlow.questions.forEach((item) => {
    if (questionFlow.answers[item.question]) return;
    const question = plainText(item.question);
    const matching = facts.filter((fact) => (termsByFact[fact.fact_key] || []).some((term) => question.includes(plainText(term))));
    if (matching.length) {
      questionFlow.answers[item.question] = matching
        .map((fact) => `${fact.fact_value} (Kaynak: ${fact.source_file_name}${fact.page_number ? `, s. ${fact.page_number}` : ""})`)
        .join("; ");
    }
  });
  renderQuestionCard();
}

function assertDocumentFlowReady() {
  if (lastDocuments.length && lastDocumentAnalysis && !els.documentApproval.checked) {
    throw new Error("Dilekçeden önce belge analizini, kaynakları ve uyarıları inceleyip onaylayın.");
  }
}

function draftReadinessIssues() {
  const issues = [];
  if (questionAnswerCount() === 0) issues.push("Dilekçe soruları henüz cevaplanmadı.");
  if (!lastDocuments.length) issues.push("Dosya evrakı yüklenmedi ve analiz edilmedi.");
  else if (!lastDocumentAnalysis) issues.push("Yüklenen dosya evrakları henüz analiz edilmedi.");
  if (!reviewWorkflowComplete) issues.push("Kaynak, emsal, delil ve risk incelemesi tamamlanmadı.");
  return issues;
}

function showDraftReadinessDialog(issues, options) {
  pendingPreliminaryDraftOptions = { ...options, preliminaryApproved: true };
  els.draftReadinessIssues.innerHTML = issues.map((issue) => `<li>${escapeHtml(issue)}</li>`).join("");
  if (!els.draftReadinessDialog.open) {
    els.draftReadinessDialog.showModal();
  }
}

async function loadDocuments() {
  const response = await apiFetch("/documents");
  if (!response.ok) throw new Error("Belge listesi alınamadı.");
  lastDocuments = await response.json();
  lastDocumentAnalysis = null;
  renderDocuments();
  renderDocumentSelection();
}

async function uploadDocuments() {
  const files = [...selectedDocumentFiles];
  if (!files.length) throw new Error("Önce yüklenecek belgeyi seçin.");

  // Her dosyanın gerçek File objesi olduğunu doğrula
  for (const file of files) {
    if (!(file instanceof File)) {
      throw new Error(`Geçersiz dosya: seçilen dosya bir File objesi değil. Lütfen dosyayı tekrar seçin.`);
    }
    if (file.size <= 0) {
      throw new Error(`"${file.name}" dosyası boş. Seçilen dosya boş olamaz.`);
    }
  }

  setBusy(true, "Belgeler güvenli alana yükleniyor...");
  try {
    // "Otomatik algıla" seçiliyse document_type hiç gönderme
    const documentTypeValue = els.documentType.value;
    const shouldSendDocumentType = documentTypeValue !== "";

    let uploadedCount = 0;
    let duplicateCount = 0;
    for (const file of files) {
      const formData = new FormData();
      // Gerçek File objesini ekle - üçüncü parametre (filename) opsiyonel
      formData.append("file", file);

      if (shouldSendDocumentType) {
        formData.append("document_type", documentTypeValue);
      }
      // "Otomatik algıla" (boş değer) seçiliyken document_type hiç gönderilmez
      // Backend default=None olarak alır ve otomatik algılar

      try {
        const uploaded = await apiUpload("/documents/upload", formData);
        lastDocuments = [uploaded, ...lastDocuments.filter((item) => item.document_id !== uploaded.document_id)];
        uploadedCount += 1;
        renderDocuments();
      } catch (error) {
        if (plainText(error.message).includes("bu belge zaten ekli")) {
          duplicateCount += 1;
          continue;
        }
        throw error;
      }
    }
    if (uploadedCount) {
      lastDocumentAnalysis = null;
      reviewWorkflowComplete = false;
      els.documentApproval.checked = false;
    }
    // Upload başarılı olduktan sonra temizle
    selectedDocumentFiles = [];
    els.documentFiles.value = "";
    renderDocumentSelection();
    renderDocuments();
    if (duplicateCount && !uploadedCount) {
      setStatus("Bu belge zaten ekli.", true);
    } else if (duplicateCount) {
      setStatus(`${uploadedCount} belge yüklendi; ${duplicateCount} belge zaten ekli olduğu için atlandı.`);
    } else {
      setStatus(`${uploadedCount} belge yüklendi. Şimdi belgeleri analiz edin.`);
    }
  } finally {
    setBusy(false);
  }
}

async function analyzeDocuments() {
  if (!lastDocuments.length) throw new Error("Önce belgeyi yükleyin.");
  setBusy(true, "Belgeler okunuyor, bilgiler kaynaklandırılıyor ve çelişkiler denetleniyor...");
  try {
    const data = await apiPost("/documents/analyze", {
      document_ids: lastDocuments.map((item) => item.document_id),
      user_claims: userClaimsFromCase(),
      document_types: {},
    });
    lastDocumentAnalysis = data;
    reviewWorkflowComplete = false;
    lastDocuments = data.documents || [];
    els.documentApproval.checked = false;
    renderDocuments();
    prefillQuestionsFromDocuments();
    renderRisks();
    renderStrategyToolkit();
    const conflictSuffix = data.conflicts?.length ? ` ${data.conflicts.length} çelişki doğrulama bekliyor.` : "";
    setStatus(`Belge analizi tamamlandı; ${data.confirmed_facts?.length || 0} bilgi kaynaklandırıldı.${conflictSuffix}`);
    return data;
  } finally {
    setBusy(false);
  }
}

async function deleteDocument(documentId) {
  const response = await apiFetch(`/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Belge silinemedi.");
  }
  lastDocuments = lastDocuments.filter((item) => item.document_id !== documentId);
  lastDocumentAnalysis = null;
  els.documentApproval.checked = false;
  renderDocuments();
  setStatus("Belge silindi. Kalan belgeler yeniden analiz edilmelidir.");
}

function renderAnalysis(data) {
  const facts = data.case_facts || [];
  const keywords = data.legal_keywords || [];
  els.analysisCount.textContent = String(facts.length + keywords.length);
  els.analysisOutput.className = "result-list";
  els.analysisOutput.innerHTML = `
    <div class="result-item">
      <h3>${escapeHtml(data.legal_topic || "Konu")}</h3>
      <div class="meta-row">
        ${keywords.map((keyword) => `<span class="chip">${escapeHtml(keyword)}</span>`).join("")}
      </div>
      <ol class="compact-list">
        ${facts.map((fact) => `<li>${escapeHtml(fact)}</li>`).join("")}
      </ol>
    </div>
  `;
}

function renderAIEnrichment(data) {
  lastCaseEnrichment = data;
  const missing = data.missing_facts || [];
  const questions = data.critical_questions || [];
  const queries = data.yargitay_query_templates || [];
  const keywords = data.search_keywords || [];
  els.analysisCount.textContent = String(missing.length + questions.length + keywords.length);
  els.analysisOutput.className = "result-list";
  els.analysisOutput.innerHTML = `
    <div class="result-item">
      <h3>${escapeHtml(data.detected_case_type || "AI olay analizi")}</h3>
      <div class="meta-row">
        <span class="chip blue">${data.ai_used ? "Gemini" : "Fallback"}</span>
        ${data.detected_practice_area ? `<span class="chip">${escapeHtml(data.detected_practice_area)}</span>` : ""}
        <span class="chip">${escapeHtml(data.confidence ?? 0)} güven</span>
      </div>
      <p>${escapeHtml(data.detected_practice_area || "Olay, dilekçe üretimi öncesinde arama ve kalite denetimi için yapılandırıldı.")}</p>
    </div>
    <div class="result-item">
      <h3>Eksik Bilgiler</h3>
      <ol class="compact-list">${missing.map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>Belirgin eksik bilgi yok.</li>"}</ol>
    </div>
    <div class="result-item">
      <h3>Kritik Sorular</h3>
      <ol class="compact-list">${questions.map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>Ek soru üretilmedi.</li>"}</ol>
    </div>
    <div class="result-item">
      <h3>Arama Sorguları</h3>
      <div class="meta-row">${queries.map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}</div>
      ${data.legal_brain_query ? `<p>${escapeHtml(data.legal_brain_query)}</p>` : ""}
    </div>
  `;
  if ((data.detected_case_type || "").toLocaleLowerCase("tr-TR").includes("araç")) {
    applyProfileRequestDefault({ petition_type: data.detected_case_type, legal_basis: data.relevant_articles || [] });
  }
}

function renderAISearch(data) {
  lastBetterSearches = data;
  els.analysisOutput.className = "result-list";
  els.analysisOutput.innerHTML = `
    <div class="result-item">
      <h3>AI Arama Sorguları</h3>
      <div class="meta-row">
        <span class="chip blue">${data.ai_used ? "Gemini" : "Fallback"}</span>
        ${(data.must_include_terms || []).map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}
      </div>
      <ol class="compact-list">${(data.yargitay_queries || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>
      ${data.legal_brain_query ? `<p>${escapeHtml(data.legal_brain_query)}</p>` : ""}
    </div>
  `;
  els.analysisCount.textContent = String((data.yargitay_queries || []).length);
}

function renderDraftAudit(data) {
  const groups = [
    ["Kritik", data.critical_issues || []],
    ["Büyük", data.major_issues || []],
    ["Dil", data.petition_language_problems || []],
    ["Emsal", data.precedent_problems || []],
    ["Kaynak", data.source_problems || []],
    ["Eksik", data.missing_facts || []],
  ];
  els.analysisOutput.className = "result-list";
  els.analysisOutput.innerHTML = `
    <div class="result-item">
      <h3>Dilekçe Kalite Kontrol</h3>
      <div class="meta-row">
        <span class="chip blue">${escapeHtml(data.quality_score)} puan</span>
        <span class="chip">${data.ai_used ? "Gemini" : "Fallback"}</span>
        <span class="chip">${data.ready_for_lawyer_review ? "İncelemeye hazır" : "Düzeltme önerilir"}</span>
      </div>
      ${groups
        .filter(([, items]) => items.length)
        .map(([, items]) => `<ol class="compact-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>`)
        .join("") || "<p>Kritik kalite sorunu bulunmadı.</p>"}
    </div>
  `;
  els.analysisCount.textContent = String(data.quality_score ?? 0);
  renderRisks({ draftAudit: data });
}

function renderBrain(data) {
  const results = [...(data.results || data.book_sources || [])].sort(
    (a, b) => Number(Boolean(b.is_directly_relevant)) - Number(Boolean(a.is_directly_relevant)),
  );
  lastBrainResults = results;
  const visibleResults = results.filter(
    (item) => item.is_directly_relevant !== false && cleanOutputText(item.usable_argument) !== UNRELATED_ARGUMENT,
  );
  const filteredCount = results.length - visibleResults.length;
  els.brainCount.textContent = String(visibleResults.length);
  if (!visibleResults.length) {
    els.brainOutput.className = "result-list";
    els.brainOutput.innerHTML = `
      <div class="result-item">
        <h3>Kaynak taraması</h3>
        <div class="meta-row">
          <span class="chip blue">${escapeHtml(results.length)} kaynak incelendi</span>
          <span class="chip">${escapeHtml(filteredCount)} kaynak filtrelendi</span>
        </div>
        <p>Bu dosya için doğrudan kullanılabilir Legal Brain kaynağı bulunamadı. Mevzuat ve Yargıtay emsalleri üzerinden devam edildi.</p>
      </div>
      ${filteredCount ? `<div class="result-item"><h3>Filtre sonucu</h3><p>Konu dışı kaynaklar filtrelendi.</p></div>` : ""}
    `;
    return;
  }
  els.brainOutput.className = "result-list";
  els.brainOutput.innerHTML = `
    ${filteredCount ? `<div class="result-item"><h3>Filtre sonucu</h3><p>Konu dışı kaynaklar filtrelendi.</p></div>` : ""}
    ${visibleResults
    .map((item) => {
      const title = item.title || item.section_title || "Kaynak";
      const score = item.relevance_score ?? "";
      const used = item.use_in_petition !== false && item.is_directly_relevant !== false;
      const preview =
        item.is_directly_relevant === false
          ? item.relevance_reason || UNRELATED_ARGUMENT
          : item.usable_argument || item.doctrine_principle || item.chunk_preview || "";
      const citation = item.citation_label || [item.author, item.page_start && `s. ${item.page_start}`].filter(Boolean).join(", ");
      const reason = item.relevance_reason || item.reason || (used ? "Somut uyuşmazlıkla doğrudan bağlantılı göründüğü için kullanılabilir." : "Konu dışı olduğu için elendi.");
      return `
        <div class="result-item">
          <h3>${escapeHtml(title)}</h3>
          <div class="meta-row">
            ${score !== "" ? `<span class="chip blue">${escapeHtml(score)} puan</span>` : ""}
            <span class="chip">${escapeHtml(item.source_type || item.kind || "kaynak")}</span>
            <span class="chip">${used ? "Dilekçede kullanılabilir" : "Dilekçede kullanılmadı"}</span>
            ${citation ? `<span class="chip">${escapeHtml(citation)}</span>` : ""}
          </div>
          <ol class="compact-list">
            <li><strong>Neden:</strong> ${escapeHtml(reason)}</li>
            <li><strong>Kullanılabilir argüman:</strong> ${escapeHtml(preview || "Bu kaynak için temiz argüman üretilemedi.")}</li>
            ${citation ? `<li><strong>Sayfa / tarih:</strong> ${escapeHtml(citation)}</li>` : ""}
          </ol>
        </div>
      `;
    })
    .join("")}
  `;
}

function cleanDecisionParagraph(item) {
  const alignment = plainText(`${item.lehe_aleyhe || ""} ${item.usefulness_score || ""}`);
  const risk = alignment.includes("riskli") || alignment.includes("aleyhe") || alignment.includes("dusuk");
  const raw = item.petition_paragraph || item.petition_usage_paragraph || item.legal_principle || item.short_summary || item.clean_text_preview || "";
  return cleanDecisionText(raw, risk ? RISK_PRECEDENT_PARAGRAPH : DEFAULT_PRECEDENT_PARAGRAPH);
}

function cleanDecisionText(value, fallback = CLEAN_PRECEDENT_EXPLANATION) {
  let text = cleanOutputText(value, fallback);
  text = text
    .replace(/İçtihat Metni/gi, "")
    .replace(/MAHKEMESİ\s*:\s*[^.]{0,160}/gi, "")
    .replace(/Kararda öne çıkan bağlantılar\s*:[^.]+\.?/gi, "")
    .replace(/Öne çıkan bağlantılar\s*:[^.]+\.?/gi, "")
    .replace(/aracın,\s*araç,\s*ayıp[^.]{0,120}/gi, "")
    .replace(/ayıp,\s*ayıplı,\s*bedel,\s*bilirkişi[^.]{0,120}/gi, "")
    .replace(/\s+/g, " ")
    .trim();
  const plain = plainText(text);
  if (
    !text ||
    plain.includes("kararda one cikan baglantilar") ||
    plain.includes("aracin arac ayip") ||
    plain.includes("ayip ayipli bedel bilirkisi") ||
    plain.includes("aracin ve aractaki ayibin")
  ) {
    return fallback;
  }
  return text;
}

function decisionScoreBreakdown(item) {
  const similarity = Math.max(0, Math.min(100, Number(item.similarity_score ?? 55)));
  const plain = plainText(`${item.short_summary || ""} ${item.legal_principle || ""} ${item.petition_paragraph || ""} ${item.lehe_aleyhe || ""}`);
  const vehicleFit = ["arac", "otomobil", "ikinci el", "motor", "servis", "ekspertiz", "tramer"].filter((term) => plain.includes(term)).length;
  const hiddenDefectFit = ["gizli ayip", "bedel indirimi", "sozlesmeden donme", "ayip ihbari"].filter((term) => plain.includes(term)).length;
  const realEstateOnly = ["tasinmaz", "konut", "daire", "bagimsiz bolum"].some((term) => plain.includes(term)) && !vehicleFit;
  const legalFit = realEstateOnly
    ? Math.min(58, similarity)
    : vehicleFit
      ? Math.min(96, 58 + vehicleFit * 5 + hiddenDefectFit * 7)
      : Math.max(45, similarity - 12);
  const currentYear = new Date().getFullYear();
  const yearMatch = String(item.date || "").match(/(20\d{2}|19\d{2})/);
  const year = yearMatch ? Number(yearMatch[1]) : currentYear - 8;
  const recency = Math.max(35, Math.min(95, 95 - Math.max(0, currentYear - year) * 4));
  const risk = plain.includes("riskli") || plain.includes("aleyhe") || plain.includes("redd") ? 35 : realEstateOnly ? 62 : 86;
  const riskLevel = risk < 50 ? "Yüksek" : risk < 75 ? "Orta" : "Düşük";
  const strength = Math.round(similarity * 0.3 + legalFit * 0.35 + recency * 0.15 + risk * 0.2);
  return { similarity, legalFit, recency, risk, riskLevel, strength };
}

function renderDecisions(data) {
  const decisions = data.top_decisions || [];
  lastDecisions = decisions;
  els.decisionCount.textContent = String(decisions.length);
  if (!decisions.length) {
    els.decisionOutput.className = "empty-state";
    els.decisionOutput.textContent = "Karar sonucu bulunamadı.";
    return;
  }
  els.decisionOutput.className = "result-list";
  els.decisionOutput.innerHTML = decisions
    .map((item) => {
      const title = item.title || `${item.court || "Yargıtay"} ${item.esas_no || ""}`;
      const detailLink = item.detail_url ? `<a href="${escapeHtml(item.detail_url)}" target="_blank" rel="noreferrer">Detay</a>` : "";
      const paragraph = cleanDecisionParagraph(item);
      const scores = decisionScoreBreakdown(item);
      const topic = item.legal_principle || item.short_summary || paragraph;
      const similar = item.why_relevant || paragraph;
      const isRisky = ["riskli", "aleyhe"].some((label) => plainText(item.lehe_aleyhe || "").includes(label));
      const different = isRisky
        ? "Süre, ihbar veya ispat yönünden somut olaydan ayrılabilir."
        : "Somut olayın belge ve tarihleri ayrıca karşılaştırılmalıdır.";
      const usage = isRisky
        ? RISK_PRECEDENT_PARAGRAPH
        : "Karar numarası, tarih ve kısa özetle destekleyici emsal olarak kullanılabilir.";
      return `
        <div class="result-item">
          <h3>${escapeHtml(title)}</h3>
          <div class="meta-row">
            <span class="chip blue">${escapeHtml(scores.strength)} güç</span>
            <span class="chip">${escapeHtml(item.lehe_aleyhe || "Değerlendirme")}</span>
            <span class="chip">${escapeHtml([item.esas_no, item.karar_no, item.date].filter(Boolean).join(" / "))}</span>
            ${detailLink ? `<span class="chip">${detailLink}</span>` : ""}
          </div>
          <ol class="compact-list">
            <li><strong>Özet:</strong> ${escapeHtml(cleanOutputText(item.short_summary || paragraph, DEFAULT_PRECEDENT_PARAGRAPH))}</li>
            <li><strong>Uyuşmazlık konusu:</strong> ${escapeHtml(cleanOutputText(topic, "Hukuki uyuşmazlık yönünden değerlendirme."))}</li>
            <li><strong>Yargıtay'ın temel değerlendirmesi:</strong> ${escapeHtml(paragraph)}</li>
            <li><strong>Somut olaya benzer yönleri:</strong> ${escapeHtml(similar)}</li>
            <li><strong>Somut olaydan ayrılan yönleri:</strong> ${escapeHtml(different)}</li>
            <li><strong>Kullanım önerisi:</strong> ${escapeHtml(usage)}</li>
          </ol>
          <div class="score-grid">
            <span>Benzerlik: ${scores.similarity}</span>
            <span>Hukuki uygunluk: ${scores.legalFit}</span>
            <span>Güncellik: ${scores.recency}</span>
            <span>Risk: ${scores.riskLevel}</span>
            <span>Genel güç: ${scores.strength}</span>
          </div>
        </div>
      `;
    })
    .join("");
}



function renderStrategy(data) {
  lastStrategy = data;
  const basis = (data.legal_basis || []).slice(0, 4).join(", ");
  els.strategyOutput.className = "strategy-output active";
  els.strategyOutput.innerHTML = `
    <strong>${escapeHtml(data.petition_type || "Dilekçe")}</strong>
    ${basis ? `<br><span>${escapeHtml(basis)}</span>` : ""}
  `;
}

function normalizeQuestionFlow(questions) {
  const incoming = (questions?.length ? questions : fallbackQuestions).map((item) =>
    typeof item === "string" ? { question: item } : { question: item.question || String(item), options: item.suggested_answers || item.options || [] },
  );
  const base = currentProfileKey() === "defectiveVehicle" ? vehicleQuestionBank : incoming;
  return [...base, ...incoming]
    .filter((item) => item.question)
    .reduce((acc, item) => {
      const key = plainText(item.question);
      if (!acc.some((existing) => plainText(existing.question) === key)) {
        acc.push({
          question: item.question,
          options: (item.options?.length ? item.options : questionOptions(item.question)).slice(0, 5),
          requiredTerms: item.requiredTerms || [],
        });
      }
      return acc;
    }, [])
    .slice(0, 10);
}

function currentQuestionItem() {
  return questionFlow.questions[questionFlow.currentIndex] || null;
}

function saveQuestionField(field) {
  const question = field?.dataset.question;
  if (!question) return;
  const value = field.value.trim();
  if (value) {
    questionFlow.answers[question] = value;
    questionFlow.skipped.delete(question);
  } else {
    delete questionFlow.answers[question];
  }
  refreshQuestionAnswerCount();
}

function answerCurrentQuestion() {
  const item = currentQuestionItem();
  if (!item) return;
  const field = Array.from(els.questionFields.querySelectorAll("[data-question]"))
    .find((candidate) => candidate.dataset.question === item.question)
    || els.questionFields.querySelector("[data-question]");
  saveQuestionField(field);
}

function questionAnswerCount() {
  return Object.values(questionFlow.answers).filter((value) => String(value).trim()).length;
}

function refreshQuestionAnswerCount() {
  els.questionFields.querySelectorAll("[data-answer-count]").forEach((element) => {
    element.textContent = `${questionAnswerCount()} cevap`;
  });
}

function renderQuestionFields(questions) {
  const previousAnswers = { ...questionFlow.answers, ...buildAnswers() };
  questionFlow = {
    questions: normalizeQuestionFlow(questions),
    currentIndex: 0,
    answers: previousAnswers,
    skipped: new Set([...questionFlow.skipped].filter((question) => !previousAnswers[question])),
    showAll: false,
  };
  renderQuestionCard();
}

function renderQuestionCard() {
  if (!questionFlow.questions.length) {
    els.questionFields.innerHTML = '<div class="question-empty">Sorular henüz hazırlanmadı.</div>';
    return;
  }
  if (questionFlow.showAll) {
    els.questionFields.innerHTML = `
      <div class="question-flow-head">
        <strong>Tüm sorular</strong>
        <span data-answer-count>${questionAnswerCount()} cevap</span>
        <button class="ghost-btn small-btn" type="button" data-action="toggle-question-mode">Kart moduna dön</button>
      </div>
      ${questionFlow.questions
        .map((item, index) => {
          const value = questionFlow.answers[item.question] || "";
          const optionButtons = (item.options || questionOptions(item.question))
            .slice(0, 5)
            .map((option) => `<button class="answer-chip" type="button" data-option="${escapeHtml(option)}">${escapeHtml(option)}</button>`)
            .join("");
          return `
            <label class="question-card compact-question-card">
              <span>${index + 1}. ${escapeHtml(item.question)}</span>
              <textarea data-question="${escapeHtml(item.question)}" rows="2">${escapeHtml(value)}</textarea>
              <div class="answer-chips">${optionButtons}</div>
            </label>
          `;
        })
        .join("")}
      <button class="primary-btn small-btn" type="button" data-action="prepare-draft-from-questions">Dilekçeyi Hazırla</button>
    `;
    return;
  }
  const item = currentQuestionItem();
  const answeredCount = questionAnswerCount();
  const progress = `${questionFlow.currentIndex + 1} / ${questionFlow.questions.length}`;
  const value = questionFlow.answers[item.question] || "";
  const optionButtons = (item.options || questionOptions(item.question))
    .slice(0, 5)
    .map((option) => `<button class="answer-chip" type="button" data-option="${escapeHtml(option)}">${escapeHtml(option)}</button>`)
    .join("");
  const isLast = questionFlow.currentIndex >= questionFlow.questions.length - 1;
  els.questionFields.innerHTML = `
    <div class="question-flow-head">
      <strong>Soru ${progress}</strong>
      <span data-answer-count>${answeredCount} cevap</span>
    </div>
    <label class="question-card active-question-card">
      <span>${escapeHtml(item.question)}</span>
      <textarea data-question="${escapeHtml(item.question)}" rows="4" placeholder="Elle yaz">${escapeHtml(value)}</textarea>
      <div class="answer-chips" aria-label="Hazır cevap seçenekleri">${optionButtons}</div>
    </label>
    <div class="question-nav">
      <button class="ghost-btn small-btn" type="button" data-action="prev-question" ${questionFlow.currentIndex === 0 ? "disabled" : ""}>Geri</button>
      <button class="ghost-btn small-btn" type="button" data-action="skip-question">Atla</button>
      <button class="primary-btn small-btn" type="button" data-action="${isLast ? "prepare-draft-from-questions" : "next-question"}">
        ${isLast ? "Dilekçeyi Hazırla" : "Sonraki"}
      </button>
    </div>
    <button class="ghost-btn small-btn full-width-btn" type="button" data-action="toggle-question-mode">Tüm soruları göster</button>
  `;
}

function resetQuestions() {
  lastStrategy = null;
  lastStrategyCase = "";
  lastStrategyRequest = "";
  questionFlow = { questions: [], currentIndex: 0, answers: {}, skipped: new Set(), showAll: false };
  els.strategyOutput.className = "strategy-output";
  els.strategyOutput.innerHTML = "";
  els.questionFields.innerHTML = '<div class="question-empty">Sorular henüz hazırlanmadı.</div>';
}

function questionsAreCurrent() {
  return (
    lastStrategy &&
    lastStrategyCase === getCaseText() &&
    lastStrategyRequest === getRequestType() &&
    els.questionFields.querySelectorAll("[data-question]").length > 0
  );
}

function buildAnswers() {
  const answers = { ...questionFlow.answers };
  els.questionFields.querySelectorAll("[data-question]").forEach((field) => {
    const question = field.dataset.question;
    const answer = field.value.trim();
    if (question && answer) {
      answers[question] = answer;
      questionFlow.answers[question] = answer;
      questionFlow.skipped.delete(question);
    } else if (question) {
      delete answers[question];
      delete questionFlow.answers[question];
    }
  });
  refreshQuestionAnswerCount();
  return answers;
}

function handleQuestionOptionClick(event) {
  const actionButton = event.target.closest("[data-action]");
  if (actionButton) {
    const action = actionButton.dataset.action;
    if (action === "prev-question") {
      answerCurrentQuestion();
      questionFlow.currentIndex = Math.max(0, questionFlow.currentIndex - 1);
      renderQuestionCard();
      renderRisks();
      return;
    }
    if (action === "next-question") {
      answerCurrentQuestion();
      questionFlow.currentIndex = Math.min(questionFlow.questions.length - 1, questionFlow.currentIndex + 1);
      renderQuestionCard();
      renderRisks();
      return;
    }
    if (action === "skip-question") {
      const item = currentQuestionItem();
      if (item) {
        delete questionFlow.answers[item.question];
        questionFlow.skipped.add(item.question);
      }
      questionFlow.currentIndex = Math.min(questionFlow.questions.length - 1, questionFlow.currentIndex + 1);
      renderQuestionCard();
      renderRisks();
      return;
    }
    if (action === "toggle-question-mode") {
      answerCurrentQuestion();
      questionFlow.showAll = !questionFlow.showAll;
      renderQuestionCard();
      return;
    }
    if (action === "prepare-draft-from-questions") {
      answerCurrentQuestion();
      runDraft({ force: true }).catch((error) => setStatus(error.message, true));
      return;
    }
  }
  const button = event.target.closest(".answer-chip");
  if (!button) return;

  const card = button.closest(".question-card");
  const field = card?.querySelector("[data-question]");
  const value = button.dataset.option;
  if (!field || !value) return;

  appendAnswerOption(field, value);
  saveQuestionField(field);
  button.classList.add("selected");
  renderRisks();
  updateFinalPetitionReadiness();
  setStatus("Seçenek cevaba eklendi.");
}

function renderDraft(data) {
  els.draftOutput.textContent = cleanOutputText(data.petition_text || data.draft_text || "");
}

function documentContextText() {
  const documents = lastDocumentAnalysis?.documents || [];
  return documents
    .flatMap((documentItem) => [
      documentItem.document_type,
      documentItem.file_name,
      ...(documentItem.extracted_facts || [])
        .filter((fact) => fact.verification_status === "fact_confirmed")
        .flatMap((fact) => [DOCUMENT_FACT_LABELS[fact.fact_key] || fact.fact_key, fact.fact_value]),
    ])
    .join(" ");
}

function missingItemResolvedByDocuments(item) {
  const keys = new Set(documentFactPayload().map((fact) => fact.fact_key));
  const value = plainText(item);
  if (value.includes("satis bedel")) return keys.has("sale_price");
  if (value.includes("satis tarih")) return keys.has("sale_date");
  if (value.includes("marka") && value.includes("model") && value.includes("plaka") && value.includes("sasi")) {
    return ["vehicle_make_model", "vehicle_plate", "vehicle_vin"].every((key) => keys.has(key));
  }
  if (value.includes("marka") || value.includes("model")) return keys.has("vehicle_make_model");
  if (value.includes("plaka")) return keys.has("vehicle_plate");
  if (value.includes("sasi") || value.includes("sase")) return keys.has("vehicle_vin");
  if (value.includes("noter")) return keys.has("notary_info");
  if (value.includes("taraf")) return keys.has("parties");
  if (value.includes("dosya numara")) return keys.has("case_number");
  return false;
}

function issueConcept(item) {
  const value = plainText(item);
  if (value.includes("satis bedel")) return "sale_price";
  if ((value.includes("marka") || value.includes("model")) && (value.includes("plaka") || value.includes("sasi"))) return "vehicle_identity";
  if (value.includes("satis tarih")) return "sale_date";
  if (value.includes("ayip ihbar") || value.includes("bildirim tarih")) return "notice";
  if (value.includes("servis") || value.includes("ekspertiz")) return "technical_report";
  return value;
}

function dedupeIssues(items) {
  const seen = new Set();
  return (items || []).map((item) => cleanOutputText(item)).filter((item) => {
    if (!item) return false;
    const concept = issueConcept(item);
    if (seen.has(concept)) return false;
    seen.add(concept);
    return true;
  });
}

function dynamicRiskState() {
  const rawCombined = [getCaseText(), getRequestType(), Object.values(buildAnswers()).join(" "), documentContextText()].join(" ");
  const combined = plainText(rawCombined);
  const profile = currentProfileKey();
  const completed = [];
  const partial = [];
  const missing = [];

  if (profile === "defectiveVehicle") {
    const hasDate = /\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b/.test(rawCombined) || /\b20\d{2}\b/.test(rawCombined);
    const hasAmount = /(?:₺|\btl\b|\blira\b|\b\d{4,}\b)/i.test(rawCombined);
    const hasSeller = ["galeri", "sirket", "gercek kisi", "tacir"].some((term) => combined.includes(term));
    const hasSaleDoc = ["noter satis", "dekont", "banka dekontu", "elden odeme"].some((term) => combined.includes(term));
    const hasVehicleMarker = ["plaka", "sasi", "marka", "model"].some((term) => combined.includes(term));
    const hasReport = ["servis raporu", "ekspertiz raporu", "rapor"].some((term) => combined.includes(term));
    const hasReportDetail = hasReport && (hasDate || /rapor\s*(no|numara|numarası)/i.test(rawCombined));
    const hasTramer = combined.includes("tramer");
    const hasNotice = ["whatsapp", "sms", "noter ihtar", "bildirim", "ihbar"].some((term) => combined.includes(term));
    const hasDemand = ["bedel iadesi", "sozlesmeden donme", "bedel indirimi", "onarim gideri", "masraf"].some((term) => combined.includes(term));

    if (hasSeller) completed.push("Satıcı sıfatı");
    else missing.push("Satıcı galeri/şirket/tacir/gerçek kişi olarak netleştirilmeli");

    if (hasSaleDoc) completed.push("Satış belgesi / ödeme dayanağı");
    else missing.push("Satış belgesi ve ödeme dayanağı eklenmeli");

    if (hasAmount) completed.push("Satış bedeli miktarı");
    else if (combined.includes("bedel")) partial.push("Satış bedeli var, miktar girilmeli");
    else missing.push("Satış bedelinin miktarı girilmeli");

    if (hasDate) completed.push("Tarih bilgisi");
    else missing.push("Satış tarihi, ayıbın öğrenilme tarihi ve bildirim tarihi somutlaştırılmalı");

    if (hasVehicleMarker && (combined.includes("plaka") || combined.includes("sasi")) && (combined.includes("marka") || combined.includes("model"))) {
      completed.push("Araç marka/model/plaka/şasi bilgisi");
    } else if (hasVehicleMarker) {
      partial.push("Araç bilgisi kısmen tamamlandı; marka-model, plaka ve şasi bilgisi somutlaştırılmalı");
    } else {
      missing.push("Araç marka-model, plaka ve şasi bilgisi somutlaştırılmalı");
    }

    if (hasReportDetail) completed.push("Servis/ekspertiz rapor bilgisi");
    else if (hasReport) partial.push("Ayıp tespit belgesi kısmen tamamlandı; servis/ekspertiz rapor tarihi ve numarası yazılmalı");
    else missing.push("Servis/ekspertiz raporu veya teknik tespit belgesi eklenmeli");

    if (hasTramer && hasDate) completed.push("TRAMER/hasar kaydı içeriği");
    else if (hasTramer) partial.push("TRAMER kaydı kısmen tamamlandı; tarih ve içerik dosyaya eklenmeli");
    else missing.push("TRAMER kaydı varsa içeriği dosyaya eklenmeli");

    if (hasNotice && hasDate) completed.push("Ayıp ihbarı tarihi ve yöntemi");
    else if (hasNotice) partial.push("Ayıp ihbarı kısmen tamamlandı; bildirim tarihi ve tebliğ/mesaj kaydı eklenmeli");
    else missing.push("Ayıp ihbarının tarihi ve yöntemi netleştirilmeli");

    if (hasDemand) completed.push("Talep stratejisi");
    else missing.push("Asli ve terditli talep stratejisi netleştirilmeli");
  } else {
    const checks = [
      ["Taraf sıfatları", ["davaci", "davali", "muvekkil"]],
      ["Talep sonucu", ["talep", "dava", "kabul"]],
      ["Deliller", ["belge", "tanik", "rapor", "kayit", "dekont"]],
    ];
    checks.forEach(([label, terms]) => {
      if (terms.some((term) => combined.includes(term))) completed.push(label);
      else missing.push(label);
    });
  }

  const skipped = [...questionFlow.skipped].map((question) => `Atlandı: ${question}`);
  const answeredCount = Object.values(buildAnswers()).filter(Boolean).length;
  const missingCount = missing.length + skipped.length;
  const riskScore = missingCount * 2 + partial.length;
  const riskLevel = riskScore >= 12 ? "Yüksek" : riskScore >= 7 ? "Orta-Yüksek" : riskScore >= 4 ? "Orta" : "Düşük";
  const riskNotes = [];
  if (profile === "defectiveVehicle" && !completed.includes("Ayıp ihbarı tarihi ve yöntemi")) {
    riskNotes.push("Ayıp ihbarı tarihi ve yöntemi netleşmezse TBK m. 223 yönünden risk doğabilir.");
  }
  if (profile === "defectiveVehicle" && !completed.includes("Servis/ekspertiz rapor bilgisi")) {
    riskNotes.push("Servis/ekspertiz/TRAMER belgesi yoksa ayıbın satış anında mevcut olduğunu ispat güçleşir.");
  }
  return { completed, partial, missing: [...missing, ...skipped], riskLevel, riskNotes, answeredCount };
}

function renderRisks({ caseEnrichment = lastCaseEnrichment, draftAudit = null, sourceAudit = null, precedentAudit = null, draftWarnings = [], draftGrounding = [] } = {}) {
  const cards = [];
  const dynamic = dynamicRiskState();
  const missing = dedupeIssues([
    ...dynamic.missing,
    ...(caseEnrichment?.missing_facts || []),
    ...(draftAudit?.missing_facts || []),
    ...documentMissingFields(),
  ].filter((item) => !missingItemResolvedByDocuments(item)));
  const riskFlags = [`Risk seviyesi: ${dynamic.riskLevel}`, ...dynamic.riskNotes, ...(caseEnrichment?.risk_flags || []), ...(draftAudit?.critical_issues || []), ...(draftAudit?.major_issues || [])];
  const rejectedSourceCount = (sourceAudit?.audited_sources || []).filter((item) => !item.use_in_petition).length;
  const sourceProblems = [
    ...(draftAudit?.source_problems || []),
    rejectedSourceCount ? "Konu dışı kaynaklar filtrelendi." : "",
  ].filter(Boolean);
  const safeDraftDecisionCount = mapSelectedDecisions().length;
  const riskyAuditItems = (precedentAudit?.audited_precedents || []).filter((item) => item.alignment === "riskli" || item.alignment === "aleyhe");
  const precedentProblems = [
    ...(draftAudit?.precedent_problems || []).filter((item) => {
      const plain = plainText(item);
      if (plain.includes("tekrar") && safeDraftDecisionCount) return false;
      if (plain.includes("riskli") && safeDraftDecisionCount) return false;
      return true;
    }),
    !safeDraftDecisionCount && lastDecisions.length ? "Emsaller bulundu; ancak güvenli biçimde dilekçeye alınabilecek doğrudan lehe emsal sınırlı." : "",
    riskyAuditItems.length && !safeDraftDecisionCount ? "Riskli/aleyhe kararlar talebi destekler gibi kullanılmadı." : "",
  ].filter(Boolean);
  const languageProblems = [...(draftAudit?.petition_language_problems || []), ...(draftWarnings || [])];
  const groundingNotes = [...(draftGrounding || []), ...((lastDraftData?.grounding_notes || []) || [])]
    .map((item) => (typeof item === "string" ? item : `[${item.status || "note"}] ${item.title || "Not"}: ${item.detail || ""}`))
    .filter(Boolean);
  const documentGrounding = documentFactPayload().map((fact) => {
    const label = DOCUMENT_FACT_LABELS[fact.fact_key] || fact.fact_key;
    return `[fact_confirmed] ${label}: ${fact.fact_value} — Kaynak: ${fact.source_file_name}${fact.page_number ? `, s. ${fact.page_number}` : ""}`;
  });
  const documentProblems = [
    ...(lastDocumentAnalysis?.warnings || []),
    ...(lastDocumentAnalysis?.conflicts || []).map((conflict) => conflict.warning),
  ];

  const pushCard = (title, items, badgeClass = "info") => {
    const cleanItems = dedupeIssues(items);
    if (!cleanItems.length) return;
    cards.push({ title, items: cleanItems, badgeClass });
  };

  pushCard("Eksik Bilgiler", missing, "warning");
  pushCard("Kısmen Tamamlananlar", dynamic.partial, "warning");
  pushCard("Tamamlananlar", dynamic.completed, "info");
  pushCard("Dava riskleri", riskFlags, "danger");
  pushCard("Emsal denetimi", precedentProblems, "warning");
  pushCard("Kaynak denetimi", sourceProblems, "warning");
  pushCard("Belge analizi", documentProblems, "warning");
  pushCard("Vakıa / kaynak grounding", [...documentGrounding, ...groundingNotes], "info");
  pushCard("Dilekçe Notları", languageProblems, "info");

  els.riskCount.textContent = String(cards.reduce((total, card) => total + card.items.length, 0));
  if (!cards.length) {
    els.riskOutput.className = "empty-state";
    els.riskOutput.textContent = "Belirgin eksik veya kritik risk bulunmadı.";
    return;
  }
  els.riskOutput.className = "risk-list";
  els.riskOutput.innerHTML = cards
    .map(
      (card) => `
        <div class="risk-card">
          <h3>${escapeHtml(card.title)} <span class="risk-badge ${card.badgeClass}">${card.items.length}</span></h3>
          <ol class="compact-list">${card.items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>
        </div>
      `,
    )
    .join("");
}

function renderReviewSummary({ analysis = null, enrichment = null, sourceCount = 0, precedentCount = 0, qualityScore = null } = {}) {
  const topic = enrichment?.detected_case_type || analysis?.legal_topic || "Hukuki inceleme";
  const keywords = enrichment?.search_keywords || analysis?.legal_keywords || [];
  els.analysisCount.textContent = String((keywords || []).length);
  els.analysisOutput.className = "result-list";
  els.analysisOutput.innerHTML = `
    <div class="result-item">
      <h3>${escapeHtml(topic)}</h3>
      <div class="meta-row">
        ${qualityScore !== null ? `<span class="chip blue">${escapeHtml(qualityScore)} kalite</span>` : ""}
        <span class="chip">${escapeHtml(sourceCount)} kaynak</span>
        <span class="chip">${escapeHtml(precedentCount)} emsal</span>
        <span class="chip">${enrichment?.ai_used ? "Gemini" : "Fallback"}</span>
      </div>
      <ol class="compact-list">
        <li>Olay analizi, kaynak taraması, emsal denetimi ve dilekçe kalite kontrolü tamamlandı.</li>
        <li>Eksik bilgi ve riskler ayrı sekmede tutuldu; dilekçe metnine ham analiz notu eklenmedi.</li>
        <li>Dilekçe sekmesindeki metin avukat kontrolüne hazır ilk taslak olarak düzenlendi.</li>
      </ol>
    </div>
    ${
      keywords.length
        ? `<div class="result-item"><h3>Anahtar kavramlar</h3><div class="meta-row">${keywords
            .slice(0, 12)
            .map((item) => `<span class="chip">${escapeHtml(item)}</span>`)
            .join("")}</div></div>`
        : ""
    }
  `;
}

function vehicleClientQuestions() {
  return [
    "Aracı hangi tarihte aldınız?",
    "Satış bedeli kaç TL?",
    "Satıcı galeri/şirket miydi, gerçek kişi miydi?",
    "Ödeme nasıl yapıldı ve dekont var mı?",
    "Araçta arıza ne zaman ortaya çıktı?",
    "Servis veya ekspertiz raporu var mı?",
    "TRAMER/hasar kaydı var mı?",
    "Satıcıya ne zaman ve nasıl bildirim yaptınız?",
    "Noter ihtarnamesi gönderildi mi?",
    "Onarım, ekspertiz ve servis masrafları kaç TL?",
  ];
}

function defenseSimulationItems() {
  if (currentProfileKey() !== "defectiveVehicle") {
    return [
      ["Somut vakıalar eksik", "Eksik tarih, belge ve deliller tamamlanmalıdır.", "Belge/tanık/resmi kayıt", "Orta"],
      ["İspat yükü davacıda", "Her vakıa delille eşleştirilmelidir.", "Delil listesi ve bilirkişi", "Orta"],
    ];
  }
  return [
    ["Araç görülerek alındı.", "Ayıp gizli niteliktedir; olağan muayene ile fark edilmesi beklenemez.", "Servis/ekspertiz raporu, bilirkişi", "Orta"],
    ["Arıza satıştan sonra oluştu.", "Arızanın satıştan önce mevcut olduğu teknik inceleme ile ispatlanmalıdır.", "Servis kayıtları, TRAMER, bilirkişi", "Yüksek"],
    ["Ayıp ihbarı süresinde yapılmadı.", "Bildirim tarihi WhatsApp, SMS, noter ihtarı veya tebliğ kayıtlarıyla somutlaştırılmalıdır.", "Yazışma, ihtarname, tebliğ şerhi", "Orta"],
    ["Satıcı ayıbı bilmiyordu.", "TBK ayıptan sorumluluk rejimi kapsamında bildirilmeyen gizli ayıp ayrıca değerlendirilmelidir.", "Satış ilanı, beyanlar, teknik kayıtlar", "Orta"],
  ];
}

function renderStrategyToolkit() {
  const dynamic = dynamicRiskState();
  const answers = buildAnswers();
  const profile = currentProfileKey();
  const hasDecisions = lastDecisions.length > 0;
  const directSources = lastBrainResults.filter((item) => item.is_directly_relevant !== false);
  const strategyGroups = [
    ["Güçlü yönler", [
      profile === "defectiveVehicle" ? "Satıcı beyanı, kısa sürede ortaya çıkan arıza ve teknik tespit birlikte kurulursa gizli ayıp anlatımı güçlenir." : "Olay, talep ve delil bağlantısı netleştirildikçe dava iskeleti güçlenir.",
      dynamic.completed.length ? `Tamamlanan bilgi başlıkları: ${dynamic.completed.join(", ")}.` : "",
    ]],
    ["Kısmen tamamlanan bilgi", dynamic.partial.length ? dynamic.partial : ["Kısmen tamamlanan başlık yok."]],
    ["Somutlaştırılması gereken bilgi", dynamic.missing.length ? dynamic.missing.map((item) => `${item}.`) : ["Belirgin kritik eksik şimdilik görünmüyor."]],
    ["Kritik eksik / görev listesi", profile === "defectiveVehicle" ? [
      "Satış tarihi ve satış bedeli somutlaştırılmalı.",
      "Araç marka/model/plaka/şasi bilgisi eklenmeli.",
      "Servis raporunun tarih, numara ve içeriği belirtilmeli.",
      "Bildirim tarihi WhatsApp/SMS veya noter ihtarıyla ispatlanmalı.",
      "TRAMER kaydı varsa içeriği dosyaya eklenmeli.",
    ] : dynamic.missing.map((item) => `${item} tamamlanmalı.`)],
    ["İspat stratejisi", profile === "defectiveVehicle" ? [
      "Servis/ekspertiz/TRAMER kayıtları ve bilirkişi incelemesi ile ayıbın niteliği ve satış anındaki varlığı ispatlanmalı.",
      "Satıcı beyanları ilan, mesaj ve tanıkla desteklenmeli.",
    ] : ["Her vakıa, belge veya tanıkla eşleştirilmeli."]],
    ["Delil tamamlama planı", [
      "Eksik bilgi başlıkları tamamlanmalı.",
      directSources.length ? "Doğrudan ilgili Legal Brain kaynakları dilekçe dayanaklarıyla kontrol edilmeli." : "Doğrudan ilgili kaynak bulunmadıysa kanun maddesi ve emsal taraması ayrıca teyit edilmeli.",
    ]],
    ["Muhtemel davalı savunmaları ve cevaplar", defenseSimulationItems().map(([defense, answer]) => `${defense} Cevap: ${answer}`)],
    ["Asli / terditli talep stratejisi", [
      profile === "defectiveVehicle" ? "Asli talep sözleşmeden dönme ve bedel iadesi; terditli talep bedel indirimi ve masrafların tahsili olarak korunmalı." : "Asli ve terditli talepler dava türüne göre açık ayrılmalı.",
    ]],
    ["Görev, yetki, süre, dava şartı", [
      profile === "defectiveVehicle" ? "Satıcının tacir/galeri olup olmadığına göre Tüketici Mahkemesi / Asliye Hukuk değerlendirmesi yapılmalı." : "Görev, yetki ve dava şartı dosya özelinde kontrol edilmeli.",
      `Güncel risk seviyesi: ${dynamic.riskLevel}.`,
    ]],
    ["Emsal kullanımı", [
      hasDecisions ? "Lehe ve doğrudan bağlantılı kararlar numara, tarih ve kısa özetle kullanılmalı; riskli kararlar dilekçeye lehe gibi alınmamalı." : "Emsal bulunmadıysa karar numarası uydurulmadan emsal bölümü boş/temkinli bırakılmalı.",
    ]],
    ["Dava açmadan önce", dynamic.missing.length ? dynamic.missing.map((item) => `${item} tamamlanmalı.`).join(" ") : "Mevcut bilgilerle ilk taslak hazırlanabilir; son kontrol avukatta olmalı."],
  ];
  els.strategyCount.textContent = String(strategyGroups.length);
  els.strategyTabOutput.className = "result-list";
  els.strategyTabOutput.innerHTML = strategyGroups
    .map(([title, items]) => {
      const list = Array.isArray(items) ? items.filter(Boolean) : [items].filter(Boolean);
      return `<div class="result-item"><h3>${escapeHtml(title)}</h3><ol class="compact-list">${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol></div>`;
    })
    .join("");

  const clientQuestions = profile === "defectiveVehicle" ? vehicleClientQuestions() : questionFlow.questions.map((item) => item.question).slice(0, 10);
  els.clientQuestionsOutput.className = "result-list";
  els.clientQuestionsOutput.innerHTML = `<div class="result-item"><h3>Müvekkile gönderilecek kısa liste</h3><ol class="compact-list">${clientQuestions
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("")}</ol></div>`;

  const defenses = defenseSimulationItems();
  els.defenseCount.textContent = String(defenses.length);
  els.defenseOutput.className = "result-list";
  els.defenseOutput.innerHTML = defenses
    .map(
      ([defense, answer, evidence, risk]) => `
        <div class="result-item">
          <h3>${escapeHtml(defense)}</h3>
          <div class="meta-row"><span class="chip blue">Risk: ${escapeHtml(risk)}</span><span class="chip">${escapeHtml(evidence)}</span></div>
          <p>${escapeHtml(answer)}</p>
        </div>
      `,
    )
    .join("");

  renderOfficialSourcesStatus();
}

function renderOfficialSourcesStatus() {
  const sources = [
    ["Resmî Gazete", "Whitelist", "Kanun ve yönetmelik değişiklikleri için resmi kaynak."],
    ["Mevzuat kaynakları", "Whitelist", "Mevzuat doğrulaması için izinli/resmî kaynak."],
    ["Yargıtay Karar Arama", "Whitelist", "Emsal karar taraması için resmî kaynak."],
    ["UYAP Emsal", "Whitelist", "UYAP emsal taraması için resmî/izinli kaynak."],
    ["Danıştay", "Whitelist", "İdari yargı içtihatları için resmî kaynak."],
    ["Anayasa Mahkemesi", "Whitelist", "AYM kararları için resmî kaynak."],
    ["Uyuşmazlık Mahkemesi", "Whitelist", "Görev uyuşmazlıkları için resmî kaynak."],
  ];
  els.officialSourceCount.textContent = String(sources.length);
  els.officialSourcesOutput.className = "result-list";
  els.officialSourcesOutput.innerHTML = `
    <div class="result-item">
      <h3>Resmî Kaynak Takibi</h3>
      <div class="meta-row">
        <span class="chip blue">Durum: Hazırlık aşamasında</span>
        <span class="chip">Canlı tarama: Kapalı</span>
        <span class="chip">Whitelist: Aktif</span>
        <span class="chip">Rastgele web taraması: Kapalı</span>
      </div>
      <ol class="compact-list">
        <li>Son kontrol: Henüz yapılmadı.</li>
        <li>Yeni kaynak: Yok.</li>
        <li>Rastgele blog, forum, haber sitesi veya izinsiz/telifli doktrin kazıması yapılmaz.</li>
      </ol>
    </div>
    ${sources
      .map(
        ([name, status, note]) => `
          <div class="result-item">
            <h3>${escapeHtml(name)}</h3>
            <div class="meta-row"><span class="chip blue">${escapeHtml(status)}</span><span class="chip">Doğrulama gerekli</span></div>
            <p>${escapeHtml(note)}</p>
          </div>
        `,
      )
      .join("")}
  `;
}

function currentDraftText() {
  const text = els.draftOutput.textContent.trim();
  if (!text || plainText(text).includes("henuz dilekce taslagi yok") || plainText(text).includes("analiz tamamlandiysa")) {
    throw new Error("Önce dilekçe taslağı oluşturmalısın.");
  }
  if (!text || text === "Henüz dilekçe taslağı yok.") {
    throw new Error("Önce dilekçe taslağı oluşturmalısın.");
  }
  return text;
}

async function runAnalysis() {
  const caseText = assertCaseText();
  setBusy(true, "Analiz yapılıyor...");
  try {
    const data = await apiPost("/case/analyze", {
      case_text: caseText,
      enriched_case_text: lastCaseEnrichment?.enriched_case_text || null,
    });
    renderAnalysis(data);
    setStatus("Analiz tamamlandı.");
    return data;
  } finally {
    setBusy(false);
  }
}

async function runAIEnrich() {
  const caseText = assertCaseText();
  setBusy(true, "AI olayı netleştiriyor...");
  try {
    const data = await apiPost("/ai/enrich-case", {
      case_text: caseText,
      practice_area: getPracticeArea() || "auto",
      use_gemini: true,
    });
    renderAIEnrichment(data);
    setStatus(data.ai_used ? "AI olay analizi hazır." : "AI fallback olay analizi hazır.");
    return data;
  } finally {
    setBusy(false);
  }
}

async function runAIQuestions() {
  const caseText = assertCaseText();
  setBusy(true, "AI soruları üretiyor...");
  try {
    const data = await apiPost("/ai/generate-legal-questions", {
      case_text: caseText,
      case_enrichment: lastCaseEnrichment || {},
      use_gemini: true,
    });
    const questions = [...(data.questions || []).map((item) => item.question), ...documentMissingQuestions()];
    lastStrategy = {
      petition_type: lastCaseEnrichment?.detected_case_type || "AI soruları",
      legal_basis: lastCaseEnrichment?.relevant_articles || [],
      missing_information_questions: questions,
    };
    renderStrategy(lastStrategy);
    renderQuestionFields(questions);
    prefillQuestionsFromDocuments();
    lastStrategyCase = caseText;
    lastStrategyRequest = getRequestType();
    setStatus(`${questions.length} AI sorusu hazır.`);
    return data;
  } finally {
    setBusy(false);
  }
}

async function runAISearch() {
  const caseText = assertCaseText();
  setBusy(true, "AI arama sorguları hazırlanıyor...");
  try {
    const data = await apiPost("/ai/build-better-searches", {
      case_text: caseText,
      case_enrichment: lastCaseEnrichment || {},
      use_gemini: true,
    });
    renderAISearch(data);
    setStatus("AI arama sorguları hazır.");
    return data;
  } finally {
    setBusy(false);
  }
}

async function runBrain() {
  const caseText = assertCaseText();
  setBusy(true, "Legal Brain aranıyor...");
  try {
    const data = await apiPost("/legal-brain/search", {
      query: lastBetterSearches?.legal_brain_query || lastCaseEnrichment?.legal_brain_query || `${caseText} ${getRequestType()}`,
      practice_area: getPracticeArea(),
      max_results: getMaxResults(),
    });
    renderBrain(data);
    setStatus("Legal Brain sonuçları hazır.");
    return data;
  } finally {
    setBusy(false);
  }
}

async function runAuditSources() {
  if (!lastBrainResults.length) {
    await runBrain();
  }
  setBusy(true, "Kaynaklar denetleniyor...");
  try {
    const audit = await apiPost("/ai/audit-sources", {
      case_enrichment: lastCaseEnrichment || { original_case_text: getCaseText(), detected_case_type: getCaseText() },
      sources: lastBrainResults,
      use_gemini: true,
    });
    const auditMap = new Map((audit.audited_sources || []).map((item) => [item.source_id, item]));
    const auditedResults = lastBrainResults
      .map((source, index) => {
        const sourceId = source.source_id || source.citation_label || source.title || `source_${index + 1}`;
        const item = auditMap.get(sourceId);
        return item
          ? {
              ...source,
              is_directly_relevant: item.is_directly_relevant,
              relevance_score: item.relevance_score,
              relevance_reason: item.reason || item.source_rejected_reason,
              usable_argument: item.use_in_petition ? source.usable_argument : UNRELATED_ARGUMENT,
              use_in_petition: item.use_in_petition,
            }
          : source;
      })
      .sort((a, b) => Number(Boolean(b.is_directly_relevant)) - Number(Boolean(a.is_directly_relevant)));
    renderBrain({ results: auditedResults, warnings: audit.warnings || [] });
    renderRisks({ sourceAudit: audit });
    setStatus("Kaynak denetimi tamamlandı.");
    return audit;
  } finally {
    setBusy(false);
  }
}

async function runYargitay() {
  const caseText = assertCaseText();
  setBusy(true, "Yargıtay kararları aranıyor...");
  try {
    const data = await apiPost("/research/yargitay", {
      case_text: `${caseText} ${getRequestType()}`,
      max_results: getMaxResults(),
      yargitay_query_templates: lastBetterSearches?.yargitay_queries || lastCaseEnrichment?.yargitay_query_templates || [],
      case_enrichment: lastCaseEnrichment || {},
    });
    renderAnalysis(data.case_analysis || {});
    renderDecisions(data);
    const errorSuffix = data.errors?.length ? ` ${data.errors.length} uyarı var.` : "";
    setStatus(`Yargıtay taraması tamamlandı.${errorSuffix}`);
    return data;
  } finally {
    setBusy(false);
  }
}

async function runAuditPrecedents() {
  if (!lastDecisions.length) {
    await runYargitay();
  }
  setBusy(true, "Emsaller denetleniyor...");
  try {
    const audit = await apiPost("/ai/audit-precedents", {
      case_text: getCaseText(),
      case_enrichment: lastCaseEnrichment || {},
      precedents: lastDecisions,
      use_gemini: true,
    });
    const auditMap = new Map((audit.audited_precedents || []).map((item) => [plainText(item.decision_id), item]));
    lastDecisions = lastDecisions
      .map((decision) => {
        const item = auditItemForDecision(auditMap, decision);
        return item
          ? {
              ...decision,
              lehe_aleyhe: item.alignment,
              usefulness_score: item.use_in_petition ? decision.usefulness_score || "Orta" : "Düşük",
              use_in_petition: item.use_in_petition,
              petition_paragraph: cleanOutputText(
                item.petition_usage_paragraph || decision.petition_paragraph,
                item.alignment === "riskli" || item.alignment === "aleyhe" ? RISK_PRECEDENT_PARAGRAPH : DEFAULT_PRECEDENT_PARAGRAPH,
              ),
              _is_duplicate: item.is_duplicate,
            }
          : decision;
      })
      .filter((decision) => !decision._is_duplicate);
    renderDecisions({ ...(lastYargitaySearch || {}), top_decisions: lastDecisions });
    renderRisks({ precedentAudit: audit });
    setStatus("Emsal denetimi tamamlandı.");
    return audit;
  } finally {
    setBusy(false);
  }
}

function mapStrategyDecisions() {
  return draftableDecisions(5).map((item) => ({
    similarity_score: item.similarity_score ?? 0,
    usefulness_score: item.usefulness_score || "orta",
    court: item.court || "Yargıtay",
    esas_no: item.esas_no || "-",
    karar_no: item.karar_no || "-",
    date: item.date || "-",
    short_summary: item.short_summary || "-",
    legal_principle: item.legal_principle || "-",
    why_relevant: item.why_relevant || "-",
    lehe_aleyhe: item.lehe_aleyhe || "Nötr",
    petition_paragraph: cleanDecisionParagraph(item),
  }));
}

function mapSelectedDecisions() {
  return draftableDecisions(3).map((item) => ({
    court: item.court || "Yargıtay",
    esas_no: item.esas_no || "-",
    karar_no: item.karar_no || "-",
    date: item.date || "-",
    petition_paragraph: cleanDecisionParagraph(item),
  }));
}

function draftableDecisions(limit = 3) {
  const preferred = lastDecisions.filter(decisionUsableForDraft);
  const fallback = lastDecisions.filter(decisionSafeForDraft);
  return (preferred.length ? preferred : fallback).slice(0, limit);
}

function decisionUsableForDraft(item) {
  if (item.use_in_petition === false) return false;
  const verification = plainText(`${item.verification_status || ""}`);
  const alignment = plainText(`${item.lehe_aleyhe || ""} ${item.petition_paragraph || ""}`);
  if (verification.includes("adverse_or_distinguishable_precedent") || alignment.includes("riskli") || alignment.includes("aleyhe")) {
    return false;
  }
  if (!verification.includes("verified_supportive_precedent")) return false;
  const usefulness = plainText(item.usefulness_score || "");
  return Number(item.similarity_score ?? 0) >= 50 && !usefulness.includes("dusuk");
}

function decisionSafeForDraft(item) {
  if (item.use_in_petition === false) return false;
  const verification = plainText(`${item.verification_status || ""}`);
  const alignment = plainText(`${item.lehe_aleyhe || ""} ${item.usefulness_score || ""} ${item.petition_paragraph || ""}`);
  if (verification.includes("adverse_or_distinguishable_precedent") || alignment.includes("riskli") || alignment.includes("aleyhe") || alignment.includes("dusuk")) return false;
  return Number(item.similarity_score ?? 0) >= 35;
}

function decisionAuditKeys(decision) {
  return [
    [decision.court || "Yargıtay", decision.esas_no || "", decision.karar_no || "", decision.date || ""].join(" | "),
    `${decision.court || "Yargıtay"}, E. ${decision.esas_no || ""}, K. ${decision.karar_no || ""}, T. ${decision.date || ""}`,
    [decision.court || "Yargıtay", decision.esas_no || "", decision.karar_no || "", decision.date || ""].join(" "),
  ].map((value) => plainText(value));
}

function auditItemForDecision(auditMap, decision) {
  for (const key of decisionAuditKeys(decision)) {
    if (auditMap.has(key)) return auditMap.get(key);
  }
  return null;
}

async function prepareQuestions(force = false) {
  const caseText = assertCaseText();
  if (!force && questionsAreCurrent()) {
    return lastStrategy;
  }
  setBusy(true, "Dilekçe soruları hazırlanıyor...");
  try {
    const data = await apiPost("/petition/strategy", {
      case_text: `${caseText} ${getRequestType()}`,
      top_decisions: mapStrategyDecisions(),
    });
    applyProfileRequestDefault(data);
    renderStrategy(data);
    renderQuestionFields([...(data.missing_information_questions || []), ...documentMissingQuestions()]);
    prefillQuestionsFromDocuments();
    lastStrategyCase = caseText;
    lastStrategyRequest = getRequestType();
    setStatus("Sorular hazır. Cevapları doldurup Dilekçe'ye tekrar bas.");
    return data;
  } finally {
    setBusy(false);
  }
}

async function runDraft(options = {}) {
  const caseText = assertCaseText();
  answerCurrentQuestion();
  assertDocumentFlowReady();
  if (!options.force && !questionsAreCurrent()) {
    await prepareQuestions(false);
    return;
  }

  const readinessIssues = finalPetitionReadinessIssues();
  if (readinessIssues.length) {
    updateFinalPetitionReadiness();
    throw new Error("Dilekçe taslağı oluşturmak için önce belge analizi ve risk/kaynak incelemesini onaylayın.");
  }

  const unresolvedMissingFacts = dedupeIssues([
    ...(lastCaseEnrichment?.missing_facts || []),
    ...documentMissingFields(),
  ].filter((item) => !missingItemResolvedByDocuments(item))).slice(0, 30);

  setBusy(true, "Dilekçe taslağı hazırlanıyor...");
  try {
    const data = await apiPost("/petition/final-draft", {
      case_text: caseText,
      case_enrichment: lastCaseEnrichment || {},
      confirmed_facts: [...new Set(lastCaseEnrichment?.confirmed_facts || [])].slice(0, 30),
      missing_facts: unresolvedMissingFacts,
      document_ids: (lastDocumentAnalysis?.documents || []).map((documentItem) => documentItem.document_id),
      document_facts: documentFactPayload(),
      petition_strategy_hint: lastCaseEnrichment?.petition_strategy_hint || "",
      answers: buildAnswers(),
      selected_decisions: mapSelectedDecisions(),
      precedent_candidates: lastDecisions,
      request_type: getRequestType(),
      use_legal_brain: true,
      legal_language_level: "usta_avukat",
      analysis_approved: els.documentApproval.checked,
      review_completed: reviewWorkflowComplete,
      legal_grounds: lastStrategy?.legal_basis || [],
      drafting_warnings: dedupeIssues([
        ...(lastCaseEnrichment?.risk_flags || []),
        ...(lastDocumentAnalysis?.warnings || []),
      ]).slice(0, 50),
    });
    lastDraftData = data;
    renderDraft(data);
    let draftAudit = null;
    if (options.auditAndRefine) {
      setStatus("Dilekçe kalite kontrolü yapılıyor...");
      draftAudit = await apiPost("/ai/audit-draft", {
        case_text: caseText,
        draft_text: currentDraftText(),
        case_enrichment: lastCaseEnrichment || {},
        selected_decisions: mapSelectedDecisions(),
        use_gemini: true,
      });
      lastDraftAudit = draftAudit;
      renderDraftAudit(draftAudit);

      if (draftAudit.can_refine && !(draftAudit.critical_issues || []).length) {
        setStatus("Usta avukat redaksiyonu deneniyor...");
        const refined = await apiPost("/ai/refine-draft", {
          case_text: caseText,
          draft_text: currentDraftText(),
          case_enrichment: lastCaseEnrichment || {},
          selected_decisions: mapSelectedDecisions(),
          use_gemini: true,
        });
        if (refined.refined_draft && refined.accepted) {
          els.draftOutput.textContent = refined.refined_draft;
        }
      } else {
        setStatus("Kritik uyarı nedeniyle redaksiyon atlandı.");
      }
    }
    renderStrategyToolkit();
    renderRisks({
      caseEnrichment: lastCaseEnrichment,
      sourceAudit: lastSourceAudit,
      precedentAudit: lastPrecedentAudit,
      draftAudit: draftAudit || lastDraftAudit,
      draftWarnings: data.warnings || [],
      draftGrounding: [],
    });
    switchTab("petition");
    const modeLabel = data.generation_mode === "gemini_mode" ? "Gemini" : "yerel güvenli şablon";
    setStatus(`Nihai dilekçe taslağı ${modeLabel} ile hazırlandı.`);
    return data;
  } finally {
    setBusy(false);
  }
}

async function runAuditDraft() {
  const draftText = currentDraftText();
  setBusy(true, "Dilekçe kalite kontrolü yapılıyor...");
  try {
    const data = await apiPost("/ai/audit-draft", {
      case_text: getCaseText(),
      draft_text: draftText,
      case_enrichment: lastCaseEnrichment || {},
      selected_decisions: mapSelectedDecisions(),
      use_gemini: true,
    });
    renderDraftAudit(data);
    setStatus(`Kalite kontrol tamamlandı: ${data.quality_score} puan.`);
    return data;
  } finally {
    setBusy(false);
  }
}

async function runRefineDraft() {
  const draftText = currentDraftText();
  setBusy(true, "Usta avukat redaksiyonu hazırlanıyor...");
  try {
    const data = await apiPost("/ai/refine-draft", {
      case_text: getCaseText(),
      draft_text: draftText,
      case_enrichment: lastCaseEnrichment || {},
      selected_decisions: mapSelectedDecisions(),
      use_gemini: true,
    });
    if (data.refined_draft) {
      els.draftOutput.textContent = data.refined_draft;
    }
    const warningSuffix = data.validator_warnings?.length ? ` ${data.validator_warnings.length} validator uyarısı var.` : "";
    setStatus(data.accepted ? `Redaksiyon hazır.${warningSuffix}` : `Redaksiyon validator’dan geçmedi; güvenli metin gösterildi.${warningSuffix}`, !data.accepted);
    return data;
  } finally {
    setBusy(false);
  }
}

async function runFullReview() {
  const caseText = assertCaseText();
  reviewWorkflowComplete = false;
  setBusy(true, "1/11 Olay analizi yapılıyor...");
  switchTab("summary");
  let analysis = null;
  let enrichment = null;
  let sourceAudit = null;
  let precedentAudit = null;
  let draftAudit = null;
  let draft = null;

  try {
    setStatus("1/11 Olay analizi yapılıyor...");
    analysis = await apiPost("/case/analyze", { case_text: caseText });
    renderAnalysis(analysis);

    setStatus("2/11 AI olay netleştirme çalışıyor...");
    enrichment = await apiPost("/ai/enrich-case", {
      case_text: caseText,
      practice_area: getPracticeArea() || "auto",
      use_gemini: true,
    });
    lastCaseEnrichment = enrichment;
    renderAIEnrichment(enrichment);
    renderRisks({ caseEnrichment: enrichment });

    setStatus("3/11 Hukuki sorular hazırlanıyor...");
    const questionData = await apiPost("/ai/generate-legal-questions", {
      case_text: caseText,
      case_enrichment: enrichment,
      use_gemini: true,
    });
    const questions = [...(questionData.questions || []).map((item) => item.question), ...documentMissingQuestions()];
    lastStrategy = {
      petition_type: enrichment.detected_case_type || "Dilekçe",
      legal_basis: enrichment.relevant_articles || [],
      missing_information_questions: questions,
    };
    applyProfileRequestDefault(lastStrategy);
    renderStrategy(lastStrategy);
    renderQuestionFields(questions);
    prefillQuestionsFromDocuments();
    lastStrategyCase = caseText;
    lastStrategyRequest = getRequestType();

    setStatus("4/11 Arama sorguları üretiliyor...");
    lastBetterSearches = await apiPost("/ai/build-better-searches", {
      case_text: caseText,
      case_enrichment: enrichment,
      use_gemini: true,
    });
    renderAISearch(lastBetterSearches);

    setStatus("5/11 Legal Brain kaynak taraması yapılıyor...");
    const brain = await apiPost("/legal-brain/search", {
      query: lastBetterSearches.legal_brain_query || enrichment.legal_brain_query || `${caseText} ${getRequestType()}`,
      practice_area: getPracticeArea(),
      max_results: getMaxResults(),
    });
    renderBrain(brain);

    setStatus("6/11 Kaynaklar denetleniyor...");
    sourceAudit = await apiPost("/ai/audit-sources", {
      case_enrichment: enrichment,
      sources: lastBrainResults,
      use_gemini: true,
    });
    lastSourceAudit = sourceAudit;
    const sourceAuditMap = new Map((sourceAudit.audited_sources || []).map((item) => [item.source_id, item]));
    const auditedSources = lastBrainResults
      .map((source, index) => {
        const sourceId = source.source_id || source.citation_label || source.title || `source_${index + 1}`;
        const item = sourceAuditMap.get(sourceId);
        return item
          ? {
              ...source,
              is_directly_relevant: item.is_directly_relevant,
              relevance_score: item.relevance_score,
              relevance_reason: item.reason || item.source_rejected_reason,
              usable_argument: item.use_in_petition ? source.usable_argument : UNRELATED_ARGUMENT,
              use_in_petition: item.use_in_petition,
            }
          : source;
      })
      .sort((a, b) => Number(Boolean(b.is_directly_relevant)) - Number(Boolean(a.is_directly_relevant)));
    renderBrain({ results: auditedSources, warnings: sourceAudit.warnings || [] });
    renderRisks({ caseEnrichment: enrichment, sourceAudit });

    setStatus("7/11 Yargıtay emsalleri aranıyor...");
    const yargitay = await apiPost("/research/yargitay", {
      case_text: `${caseText} ${getRequestType()}`,
      max_results: getMaxResults(),
      yargitay_query_templates: lastBetterSearches.yargitay_queries || enrichment.yargitay_query_templates || [],
      case_enrichment: enrichment,
    });
    renderDecisions(yargitay);

    setStatus("8/11 Emsaller denetleniyor...");
    precedentAudit = await apiPost("/ai/audit-precedents", {
      case_text: caseText,
      case_enrichment: enrichment,
      precedents: lastDecisions,
      use_gemini: true,
    });
    lastPrecedentAudit = precedentAudit;
    const precedentAuditMap = new Map((precedentAudit.audited_precedents || []).map((item) => [plainText(item.decision_id), item]));
    lastDecisions = lastDecisions
      .map((decision) => {
        const item = auditItemForDecision(precedentAuditMap, decision);
        return item
          ? {
              ...decision,
              lehe_aleyhe: item.alignment,
              usefulness_score: item.use_in_petition ? decision.usefulness_score || "Orta" : "Düşük",
              use_in_petition: item.use_in_petition,
              petition_paragraph: cleanOutputText(
                item.petition_usage_paragraph || decision.petition_paragraph,
                item.alignment === "riskli" || item.alignment === "aleyhe" ? RISK_PRECEDENT_PARAGRAPH : DEFAULT_PRECEDENT_PARAGRAPH,
              ),
              _is_duplicate: item.is_duplicate,
            }
          : decision;
      })
      .filter((decision) => !decision._is_duplicate);
    renderDecisions({ ...yargitay, top_decisions: lastDecisions });
    renderRisks({ caseEnrichment: enrichment, sourceAudit, precedentAudit });
    renderStrategyToolkit();
    renderReviewSummary({
      analysis,
      enrichment,
      sourceCount: lastBrainResults.length,
      precedentCount: lastDecisions.length,
      qualityScore: null,
    });
    reviewWorkflowComplete = true;
    updateFinalPetitionReadiness();
    switchTab("summary");
    setStatus("Kaynak ve emsal incelemesi hazır. Soru kartlarını cevaplayıp son kartta Dilekçeyi Hazırla'ya bas.");
  } finally {
    setBusy(false);
  }
}

async function copyDraft() {
  const text = els.draftOutput.textContent.trim();
  if (!text || plainText(text).includes("analiz tamamlandiysa")) return;
  await navigator.clipboard.writeText(text);
  setStatus("Taslak panoya kopyalandı.");
}

function downloadDraft() {
  const text = els.draftOutput.textContent.trim();
  if (!text || plainText(text).includes("analiz tamamlandiysa")) return;
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "dilekce-taslagi.txt";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function downloadBlob(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function printDraft() {
  const text = currentDraftText();
  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    setStatus("Yazdırma penceresi açılamadı.", true);
    return;
  }
  printWindow.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Dilekçe</title><style>body{background:#f3f4f6;margin:0;padding:24px;font-family:Georgia,'Times New Roman',serif}.page{width:210mm;min-height:297mm;margin:auto;background:white;padding:25mm 22mm;box-shadow:0 0 0 1px #ddd;white-space:pre-wrap;line-height:1.6;color:#111827}@media print{body{background:white;padding:0}.page{box-shadow:none;margin:0;width:auto;min-height:auto}}</style></head><body><div class="page">${escapeHtml(text)}</div></body></html>`);
  printWindow.document.close();
  printWindow.focus();
  printWindow.print();
}

function downloadDocx() {
  const text = currentDraftText();
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Dilekçe</title></head><body><pre style="font-family:Georgia,'Times New Roman',serif;white-space:pre-wrap;line-height:1.6">${escapeHtml(text)}</pre></body></html>`;
  downloadBlob("dilekce-taslagi.doc", html, "application/msword;charset=utf-8");
  setStatus("Word uyumlu DOC çıktısı hazırlandı; DOCX servis modülü için altyapı ayrıldı.");
}

function downloadPdf() {
  printDraft();
  setStatus("PDF için yazdır penceresinde 'PDF olarak kaydet' seçilebilir.");
}

function downloadUdf() {
  const text = currentDraftText();
  const udf = `<?xml version="1.0" encoding="UTF-8"?>\n<emsalist-udf-placeholder>\n  <type>dilekce</type>\n  <note>UYAP UDF üretim modülü için placeholder çıktıdır.</note>\n  <content><![CDATA[${text}]]></content>\n</emsalist-udf-placeholder>\n`;
  downloadBlob("dilekce-udf-placeholder.xml", udf, "application/xml;charset=utf-8");
}

async function copyClientQuestions() {
  const text = (els.clientQuestionsOutput.innerText || "").trim();
  if (!text) return;
  await navigator.clipboard.writeText(text);
  setStatus("Müvekkil soru listesi panoya kopyalandı.");
}

function clearAll() {
  els.caseText.value = "";
  els.requestType.value = "Talebimizin kabulü";
  lastDecisions = [];
  lastBrainResults = [];
  lastCaseEnrichment = null;
  lastBetterSearches = null;
  lastYargitaySearch = null;
  lastDraftData = null;
  lastDraftAudit = null;
  lastSourceAudit = null;
  lastPrecedentAudit = null;
  reviewWorkflowComplete = false;
  lastDocumentAnalysis = null;
  selectedDocumentFiles = [];
  els.documentFiles.value = "";
  els.documentApproval.checked = false;
  resetQuestions();
  els.analysisCount.textContent = "0";
  els.brainCount.textContent = "0";
  els.decisionCount.textContent = "0";
  els.riskCount.textContent = "0";
  els.strategyCount.textContent = "0";
  els.defenseCount.textContent = "0";
  els.officialSourceCount.textContent = "0";
  els.analysisOutput.className = "empty-state";
  els.brainOutput.className = "empty-state";
  els.decisionOutput.className = "empty-state";
  els.riskOutput.className = "empty-state";
  els.strategyTabOutput.className = "empty-state";
  els.clientQuestionsOutput.className = "empty-state";
  els.defenseOutput.className = "empty-state";
  els.officialSourcesOutput.className = "empty-state";
  els.analysisOutput.textContent = "Henüz analiz yok.";
  els.brainOutput.textContent = "Henüz kaynak sonucu yok.";
  els.decisionOutput.textContent = "Henüz karar sonucu yok.";
  els.draftOutput.textContent = "Analiz tamamlandıysa “Dilekçe Taslağı Hazırla” butonuyla nihai taslak oluşturabilirsiniz.";
  els.riskOutput.textContent = "Henüz risk değerlendirmesi yok.";
  els.strategyTabOutput.textContent = "Henüz strateji hazırlanmadı.";
  els.clientQuestionsOutput.textContent = "Henüz müvekkil soru listesi yok.";
  els.defenseOutput.textContent = "Henüz savunma simülasyonu yok.";
  els.officialSourcesOutput.textContent = "Henüz resmî kaynak takibi yok.";
  switchTab("summary");
  renderDocuments();
  renderDocumentSelection();
  updateFinalPetitionReadiness();
  setStatus("");
}

async function checkHealth() {
  try {
    const response = await apiFetch("/health");
    if (!response.ok) throw new Error("health");
    els.healthPill.textContent = "API hazır";
    els.healthPill.className = "status-pill ok";
  } catch {
    els.healthPill.textContent = "API bağlantısı yok";
    els.healthPill.className = "status-pill bad";
  }
}

function updateApiLinks() {
  document.querySelectorAll("[data-api-link]").forEach((link) => {
    link.href = apiUrl(link.dataset.apiLink);
  });
}

function wireEvents() {
  updateApiLinks();
  initTheme();
  els.themeToggle?.addEventListener("change", () => applyTheme(els.themeToggle.checked ? "dark" : "light"));
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });
  els.questionFields.addEventListener("click", handleQuestionOptionClick);
  els.questionFields.addEventListener("input", (event) => {
    const field = event.target.closest("[data-question]");
    if (field) saveQuestionField(field);
    renderRisks();
    updateFinalPetitionReadiness();
  });
  els.analysisOutput.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action='use-ai-enrichment']");
    if (!button || !lastCaseEnrichment) return;
    const enrichment = lastCaseEnrichment;
    if (enrichment.enriched_case_text) {
      setFieldValue(els.caseText, enrichment.enriched_case_text);
      lastCaseEnrichment = enrichment;
    }
    lastStrategy = {
      petition_type: enrichment.detected_case_type || "AI analiz",
      legal_basis: enrichment.relevant_articles || [],
      missing_information_questions: enrichment.critical_questions || [],
    };
    renderStrategy(lastStrategy);
    renderQuestionFields(enrichment.critical_questions || []);
    lastStrategyCase = getCaseText();
    lastStrategyRequest = getRequestType();
    setStatus("AI analizi aktif akışa alındı.");
  });
  els.documentFiles.addEventListener("change", () => {
    // Gerçek File objelerini state'te sakla
    selectedDocumentFiles = Array.from(els.documentFiles.files || []);
    renderDocumentSelection();
    if (selectedDocumentFiles.length) {
      setStatus(`${selectedDocumentFiles.length} dosya seçildi. Backend'e göndermek için Belgeleri Yükle'ye basın.`);
    }
  });
  $("uploadDocumentsBtn").addEventListener("click", () => uploadDocuments().catch((error) => setStatus(error.message, true)));
  $("analyzeDocumentsBtn").addEventListener("click", () => analyzeDocuments().catch((error) => setStatus(error.message, true)));
  els.documentOutput.addEventListener("click", (event) => {
    const button = event.target.closest("[data-delete-document]");
    if (!button) return;
    const documentId = button.dataset.deleteDocument;
    if (!window.confirm("Bu belgeyi kalıcı olarak silmek istiyor musunuz?")) return;
    deleteDocument(documentId).catch((error) => setStatus(error.message, true));
  });
  $("cancelPreliminaryDraftBtn").addEventListener("click", () => {
    pendingPreliminaryDraftOptions = null;
    els.draftReadinessDialog.close();
    setStatus("Dilekçe üretilmedi. Önce kritik bilgi, belge ve inceleme adımlarını tamamlayın.", true);
  });
  $("confirmPreliminaryDraftBtn").addEventListener("click", () => {
    const options = pendingPreliminaryDraftOptions;
    pendingPreliminaryDraftOptions = null;
    els.draftReadinessDialog.close();
    if (options) runDraft(options).catch((error) => setStatus(error.message, true));
  });
  els.draftReadinessDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    pendingPreliminaryDraftOptions = null;
    els.draftReadinessDialog.close();
    setStatus("Dilekçe üretilmedi. Önce kritik bilgi, belge ve inceleme adımlarını tamamlayın.", true);
  });
  $("reviewBtn").addEventListener("click", () => runFullReview().catch((error) => setStatus(error.message, true)));
  $("finalPetitionBtn").addEventListener("click", () => runDraft({ force: true }).catch((error) => setStatus(error.message, true)));
  $("aiEnrichBtn").addEventListener("click", () => runAIEnrich().catch((error) => setStatus(error.message, true)));
  $("aiQuestionsBtn").addEventListener("click", () => runAIQuestions().catch((error) => setStatus(error.message, true)));
  $("aiSearchBtn").addEventListener("click", () => runAISearch().catch((error) => setStatus(error.message, true)));
  $("analyzeBtn").addEventListener("click", () => runAnalysis().catch((error) => setStatus(error.message, true)));
  $("brainBtn").addEventListener("click", () => runBrain().catch((error) => setStatus(error.message, true)));
  $("auditSourcesBtn").addEventListener("click", () => runAuditSources().catch((error) => setStatus(error.message, true)));
  $("yargitayBtn").addEventListener("click", () => runYargitay().catch((error) => setStatus(error.message, true)));
  $("auditPrecedentsBtn").addEventListener("click", () => runAuditPrecedents().catch((error) => setStatus(error.message, true)));
  $("questionsBtn").addEventListener("click", () => prepareQuestions(true).catch((error) => setStatus(error.message, true)));
  $("draftBtn").addEventListener("click", () => runDraft().catch((error) => setStatus(error.message, true)));
  $("auditDraftBtn").addEventListener("click", () => runAuditDraft().catch((error) => setStatus(error.message, true)));
  $("refineDraftBtn").addEventListener("click", () => runRefineDraft().catch((error) => setStatus(error.message, true)));
  $("sampleBtn").addEventListener("click", () => {
    els.caseText.value =
      "Müvekkil, ikinci el aracı satıcının kazasız, ağır hasarsız ve sorunsuz olduğu yönündeki beyanlarına güvenerek noter satışıyla satın aldı. Teslimden kısa süre sonra araçta motor arızası ortaya çıktı; servis incelemesinde arızanın önceki onarım ve gizli hasar kaydıyla bağlantılı olabileceği bildirildi. Müvekkil durumu öğrenir öğrenmez satıcıya WhatsApp üzerinden bildirdi, ancak satıcı sorumluluk kabul etmedi. Sözleşmeden dönme ve satış bedelinin iadesi, aksi halde bedel indirimi ile servis, ekspertiz ve onarım giderlerinin tahsili istenmektedir.";
    els.practiceArea.value = "BorÃ§lar hukuku";
    els.requestType.value = "İhtiyaç nedeniyle kiralananın tahliyesine karar verilmesi";
    els.requestType.value = defectiveVehicleRequest;
    lastDecisions = [];
    resetQuestions();
    setStatus("Örnek olay yüklendi.");
  });
  $("clearBtn").addEventListener("click", clearAll);
  $("copyDraftBtn").addEventListener("click", () => copyDraft().catch((error) => setStatus(error.message, true)));
  $("downloadDraftBtn").addEventListener("click", downloadDraft);
  $("printDraftBtn")?.addEventListener("click", () => {
    try {
      printDraft();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
  $("downloadDocxBtn")?.addEventListener("click", () => {
    try {
      downloadDocx();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
  $("downloadPdfBtn")?.addEventListener("click", () => {
    try {
      downloadPdf();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
  $("downloadUdfBtn")?.addEventListener("click", () => {
    try {
      downloadUdf();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
  $("copyClientQuestionsBtn")?.addEventListener("click", () => copyClientQuestions().catch((error) => setStatus(error.message, true)));
  els.caseText.addEventListener("input", () => {
    lastStrategyCase = "";
    lastCaseEnrichment = null;
    lastBetterSearches = null;
    lastYargitaySearch = null;
    reviewWorkflowComplete = false;
  });
  els.requestType.addEventListener("input", () => {
    lastStrategyRequest = "";
    reviewWorkflowComplete = false;
  });
  els.documentApproval.addEventListener("change", updateFinalPetitionReadiness);
}

wireEvents();
renderOfficialSourcesStatus();
checkHealth();
loadDocuments().catch((error) => setStatus(error.message, true));
