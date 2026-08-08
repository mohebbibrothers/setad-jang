/* global django */
(function () {
  "use strict";

  const GREGORIAN_MONTHS = [
    "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
    "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
  ];
  const JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
  ];
  const MIN_GREGORIAN_YEAR = 1900;
  const MAX_GREGORIAN_YEAR = 2100;
  const MIN_JALALI_YEAR = 1278;
  const MAX_JALALI_YEAR = 1479;

  function div(a, b) {
    return ~~(a / b);
  }

  function gregorianToDayNumber(year, month, day) {
    const gy = year - 1600;
    const gm = month - 1;
    const gd = day - 1;
    const gMonthDays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let dayNo = 365 * gy + div(gy + 3, 4) - div(gy + 99, 100) + div(gy + 399, 400);
    for (let i = 0; i < gm; ++i) dayNo += gMonthDays[i];
    if (gm > 1 && ((gy + 1600) % 4 === 0 && ((gy + 1600) % 100 !== 0 || (gy + 1600) % 400 === 0))) dayNo += 1;
    return dayNo + gd;
  }

  function gregorianToJalali(year, month, day) {
    let dayNo = gregorianToDayNumber(year, month, day);
    let jDayNo = dayNo - 79;
    const jNp = div(jDayNo, 12053);
    jDayNo %= 12053;
    let jy = 979 + 33 * jNp + 4 * div(jDayNo, 1461);
    jDayNo %= 1461;
    if (jDayNo >= 366) {
      jy += div(jDayNo - 1, 365);
      jDayNo = (jDayNo - 1) % 365;
    }
    const jm = jDayNo < 186 ? 1 + div(jDayNo, 31) : 7 + div(jDayNo - 186, 30);
    const jd = 1 + (jDayNo < 186 ? jDayNo % 31 : (jDayNo - 186) % 30);
    return { year: jy, month: jm, day: jd };
  }

  function jalaliToGregorian(year, month, day) {
    const jy = year - 979;
    const jm = month - 1;
    const jd = day - 1;
    const jMonthDays = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29];
    let jDayNo = 365 * jy + div(jy, 33) * 8 + div((jy % 33) + 3, 4);
    for (let i = 0; i < jm; ++i) jDayNo += jMonthDays[i];
    jDayNo += jd;
    let gDayNo = jDayNo + 79;
    let gy = 1600 + 400 * div(gDayNo, 146097);
    gDayNo %= 146097;
    let leap = true;
    if (gDayNo >= 36525) {
      gDayNo--;
      gy += 100 * div(gDayNo, 36524);
      gDayNo %= 36524;
      if (gDayNo >= 365) gDayNo++;
      else leap = false;
    }
    gy += 4 * div(gDayNo, 1461);
    gDayNo %= 1461;
    if (gDayNo >= 366) {
      leap = false;
      gDayNo--;
      gy += div(gDayNo, 365);
      gDayNo %= 365;
    }
    const gMonthDays = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let gm = 0;
    while (gm < 12 && gDayNo >= gMonthDays[gm]) {
      gDayNo -= gMonthDays[gm];
      gm++;
    }
    return { year: gy, month: gm + 1, day: gDayNo + 1 };
  }

  function pad(value) {
    return String(value).padStart(2, "0");
  }

  function toIsoDate(year, month, day) {
    return `${year}-${pad(month)}-${pad(day)}`;
  }

  function parseIsoDate(value) {
    const match = String(value || "").trim().match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
    if (!match) return null;
    return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
  }

  function daysInGregorianMonth(year, month) {
    return new Date(year, month, 0).getDate();
  }

  function isJalaliLeapYear(year) {
    const breaks = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178];
    let gy = year + 621;
    let leapJ = -14;
    let jp = breaks[0];
    let jm;
    let jump;
    for (let i = 1; i < breaks.length; i += 1) {
      jm = breaks[i];
      jump = jm - jp;
      if (year < jm) break;
      leapJ += div(jump, 33) * 8 + div((jump % 33), 4);
      jp = jm;
    }
    let n = year - jp;
    leapJ += div(n, 33) * 8 + div(((n % 33) + 3), 4);
    if ((jump % 33) === 4 && jump - n === 4) leapJ += 1;
    const leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
    const march = 20 + leapJ - leapG;
    if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33;
    let leap = (((n + 1) % 33) - 1) % 4;
    if (leap === -1) leap = 4;
    return { leap: leap === 0, march: march };
  }

  function daysInJalaliMonth(year, month) {
    if (month <= 6) return 31;
    if (month <= 11) return 30;
    return isJalaliLeapYear(year).leap ? 30 : 29;
  }

  function option(value, label, selected) {
    const item = document.createElement("option");
    item.value = String(value);
    item.textContent = label;
    if (selected) item.selected = true;
    return item;
  }

  function fillSelect(select, values, selectedValue) {
    select.textContent = "";
    values.forEach((item) => select.appendChild(option(item.value, item.label, String(item.value) === String(selectedValue))));
  }

  function range(start, end) {
    const values = [];
    for (let year = start; year <= end; year += 1) values.push({ value: year, label: String(year) });
    return values;
  }

  function monthOptions(months) {
    return months.map((name, index) => ({ value: index + 1, label: `${index + 1} — ${name}` }));
  }

  function dayOptions(count) {
    return range(1, count);
  }

  function createField(labelText, element) {
    const wrapper = document.createElement("div");
    wrapper.className = "sj-date-field";
    const label = document.createElement("label");
    label.textContent = labelText;
    wrapper.appendChild(label);
    wrapper.appendChild(element);
    return wrapper;
  }

  function getInputDate(input) {
    const parsed = parseIsoDate(input.value);
    if (parsed) return parsed;
    const today = new Date();
    return { year: today.getFullYear(), month: today.getMonth() + 1, day: today.getDate() };
  }

  function enhanceDateInput(input) {
    if (!input || input.dataset.sjDualCalendar === "1") return;
    input.dataset.sjDualCalendar = "1";
    input.setAttribute("autocomplete", "off");

    const wrapper = document.createElement("span");
    wrapper.className = "sj-date-enhanced";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sj-date-trigger";
    button.textContent = "تقویم پیشرفته";
    const summary = document.createElement("span");
    summary.className = "sj-date-summary";
    wrapper.appendChild(button);
    wrapper.appendChild(summary);
    input.insertAdjacentElement("afterend", wrapper);

    const popover = document.createElement("div");
    const useInlinePopover = Boolean(input.closest(".inline-group, .inline-related"));
    popover.className = useInlinePopover ? "sj-date-popover sj-date-popover-inline" : "sj-date-popover";
    popover.hidden = true;
    document.body.appendChild(popover);

    const calendarType = document.createElement("select");
    const year = document.createElement("select");
    const month = document.createElement("select");
    const day = document.createElement("select");

    const grid = document.createElement("div");
    grid.className = "sj-date-grid";
    grid.appendChild(createField("نوع تقویم", calendarType));
    grid.appendChild(createField("سال", year));
    grid.appendChild(createField("ماه", month));
    grid.appendChild(createField("روز", day));

    const actions = document.createElement("div");
    actions.className = "sj-date-actions";
    const apply = document.createElement("button");
    apply.type = "button";
    apply.className = "sj-date-primary";
    apply.textContent = "اعمال تاریخ";
    const today = document.createElement("button");
    today.type = "button";
    today.className = "sj-date-secondary";
    today.textContent = "امروز";
    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "sj-date-secondary";
    clear.textContent = "پاک کردن";
    const close = document.createElement("button");
    close.type = "button";
    close.className = "sj-date-secondary";
    close.textContent = "بستن";
    actions.append(apply, today, clear, close);

    const help = document.createElement("div");
    help.className = "sj-date-help";
    help.textContent = "تقویم شمسی یا میلادی را انتخاب کنید؛ سال مستقیم از فهرست انتخاب می‌شود و دیگر نیازی به ورق زدن ماه‌ها نیست. مقدار ذخیره‌شده برای Django همیشه میلادی ISO است.";

    popover.append(grid, actions, help);

    fillSelect(calendarType, [{ value: "jalali", label: "شمسی" }, { value: "gregorian", label: "میلادی" }], "jalali");

    function selectedType() {
      return calendarType.value;
    }

    function syncSummary() {
      const g = parseIsoDate(input.value);
      if (!g) {
        summary.textContent = "";
        return;
      }
      const j = gregorianToJalali(g.year, g.month, g.day);
      summary.textContent = `میلادی ${toIsoDate(g.year, g.month, g.day)} / شمسی ${j.year}/${pad(j.month)}/${pad(j.day)}`;
    }

    function populateFromInput(type) {
      const g = getInputDate(input);
      if (type === "jalali") {
        const j = gregorianToJalali(g.year, g.month, Math.min(g.day, daysInGregorianMonth(g.year, g.month)));
        fillSelect(year, range(MIN_JALALI_YEAR, MAX_JALALI_YEAR), j.year);
        fillSelect(month, monthOptions(JALALI_MONTHS), j.month);
        fillSelect(day, dayOptions(daysInJalaliMonth(j.year, j.month)), Math.min(j.day, daysInJalaliMonth(j.year, j.month)));
      } else {
        fillSelect(year, range(MIN_GREGORIAN_YEAR, MAX_GREGORIAN_YEAR), g.year);
        fillSelect(month, monthOptions(GREGORIAN_MONTHS), g.month);
        fillSelect(day, dayOptions(daysInGregorianMonth(g.year, g.month)), Math.min(g.day, daysInGregorianMonth(g.year, g.month)));
      }
    }

    function refreshDays() {
      const type = selectedType();
      const y = Number(year.value);
      const m = Number(month.value);
      const currentDay = Number(day.value || 1);
      const count = type === "jalali" ? daysInJalaliMonth(y, m) : daysInGregorianMonth(y, m);
      fillSelect(day, dayOptions(count), Math.min(currentDay, count));
    }

    function positionPopover() {
      // The popover is appended to body, then positioned near the trigger with
      // viewport clamping. This keeps the previous contextual UX while avoiding
      // clipping inside Django StackedInline/TabularInline containers.
      const rect = button.getBoundingClientRect();
      const margin = 8;
      const width = popover.offsetWidth || 440;
      const height = popover.offsetHeight || 360;
      const viewportWidth = document.documentElement.clientWidth;
      const viewportHeight = document.documentElement.clientHeight;

      let left = rect.left;
      if (document.documentElement.dir === "rtl") {
        left = rect.right - width;
      }
      left = Math.max(margin, Math.min(left, viewportWidth - width - margin));

      let top = rect.bottom + margin;
      if (top + height > viewportHeight - margin) {
        top = rect.top - height - margin;
      }
      top = Math.max(margin, Math.min(top, viewportHeight - height - margin));

      popover.style.left = `${left}px`;
      popover.style.top = `${top}px`;
    }

    let lastToggleAt = 0;
    let suppressDocumentCloseUntil = 0;

    function openPopover() {
      try {
        populateFromInput(selectedType());
        popover.hidden = false;
        popover.style.display = "block";
        button.setAttribute("aria-expanded", "true");
        suppressDocumentCloseUntil = Date.now() + 350;
        // Wait one frame so browsers compute dimensions even inside complex
        // Django admin inline/form layouts before viewport clamping.
        window.requestAnimationFrame(positionPopover);
      } catch (error) {
        // Do not fail silently for admin users; surface a compact diagnostic in
        // DevTools while keeping the original date input usable.
        console.error("Setad Jang admin calendar failed to open", error);
      }
    }

    function closePopover() {
      popover.hidden = true;
      popover.style.display = "";
      button.setAttribute("aria-expanded", "false");
    }

    function togglePopover(event) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation?.();
      const now = Date.now();
      if (now - lastToggleAt < 250) return;
      lastToggleAt = now;
      if (popover.hidden) openPopover();
      else closePopover();
    }

    calendarType.addEventListener("change", () => populateFromInput(selectedType()));
    year.addEventListener("change", refreshDays);
    month.addEventListener("change", refreshDays);
    button.setAttribute("aria-haspopup", "dialog");
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("pointerdown", togglePopover, { capture: true });
    button.addEventListener("mousedown", togglePopover, { capture: true });
    button.addEventListener("click", togglePopover, { capture: true });
    close.addEventListener("click", (event) => {
      event.preventDefault();
      closePopover();
    });
    clear.addEventListener("click", () => {
      input.value = "";
      input.dispatchEvent(new Event("change", { bubbles: true }));
      syncSummary();
      closePopover();
    });
    today.addEventListener("click", () => {
      const now = new Date();
      input.value = toIsoDate(now.getFullYear(), now.getMonth() + 1, now.getDate());
      input.dispatchEvent(new Event("change", { bubbles: true }));
      syncSummary();
      populateFromInput(selectedType());
    });
    apply.addEventListener("click", () => {
      const y = Number(year.value);
      const m = Number(month.value);
      const d = Number(day.value);
      const g = selectedType() === "jalali" ? jalaliToGregorian(y, m, d) : { year: y, month: m, day: d };
      input.value = toIsoDate(g.year, g.month, g.day);
      input.dispatchEvent(new Event("change", { bubbles: true }));
      syncSummary();
      closePopover();
    });
    input.addEventListener("change", syncSummary);
    window.addEventListener("resize", () => { if (!popover.hidden) positionPopover(); });
    document.addEventListener("pointerdown", (event) => {
      if (popover.hidden) return;
      if (Date.now() < suppressDocumentCloseUntil) return;
      if (popover.contains(event.target) || wrapper.contains(event.target)) return;
      closePopover();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !popover.hidden) closePopover();
    });
    syncSummary();
  }

  function enhanceAll() {
    document.querySelectorAll("input.vDateField").forEach(enhanceDateInput);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceAll);
  } else {
    enhanceAll();
  }

  if (window.MutationObserver) {
    const observer = new MutationObserver(enhanceAll);
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }
}());
