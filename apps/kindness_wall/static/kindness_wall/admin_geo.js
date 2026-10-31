/**
 * ───────────────────────────────────────────────────────────────────────────
 * geo-admin.js — دراپ‌دانِ وابستهٔ «استان → شهر → روستا/محله» در پنلِ ادمین
 *
 * مسئله: استان و شهر باید از فهرستِ رسمی انتخاب شوند (نه تایپِ آزاد)، و
 * شهرهای هر استان باید بعد از انتخابِ استان باز شوند. `admin/kindness_wall/
 * kindnesslisting/change/` نقشهٔ کاملِ «استان → شهرها» را در یک <script
 * type="application/json"> تزریق می‌کند (همان دادهٔ دیتاستِ بک‌اند؛ بدونِ
 * درخواستِ شبکه، پس در پنلِ کند هم فوری است).
 *
 * رفتار:
 *   • استان خالی ⇒ شهر خالی و غیرفعال با برچسبِ «ابتدا استان را انتخاب کنید».
 *   • استان انتخاب‌شده ⇒ گزینه‌های شهر همان استان (به‌ترتیبِ الفبا) + «همهٔ
 *     شهرهای این استان» (مقدارِ خالی) + حفظِ مقدارِ فعلی اگر در فهرست نبود
 *     (تا ویرایشِ رکوردهای قدیمی چیزی را بی‌صدا پاک نکند).
 *   • اگر دیتاستِ روستا متصل باشد، ورودیِ روستا به datalist تبدیل می‌شود.
 * ───────────────────────────────────────────────────────────────────────────
 */
(function () {
  'use strict';

  function onReady(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  onReady(function () {
    var dataEl = document.getElementById('kw-geo-data');
    var provinceSelect = document.getElementById('id_province');
    var citySelect = document.getElementById('id_city');
    var localityInput = document.getElementById('id_locality');
    if (!dataEl || !provinceSelect || !citySelect) return;

    var payload;
    try {
      payload = JSON.parse(dataEl.textContent || '{}');
    } catch (err) {
      return;
    }
    var cities = payload.cities || {};
    var localities = payload.localities || {};

    function option(value, label) {
      var el = document.createElement('option');
      el.value = value;
      el.textContent = label;
      return el;
    }

    function rebuildCities(keepValue) {
      var province = provinceSelect.value;
      var previous = keepValue !== undefined ? keepValue : citySelect.value;
      citySelect.innerHTML = '';

      if (!province) {
        citySelect.appendChild(option('', '— ابتدا استان را انتخاب کنید —'));
        citySelect.disabled = true;
        rebuildLocalities('');
        return;
      }

      citySelect.disabled = false;
      citySelect.appendChild(option('', '— همهٔ شهرهای ' + province + ' —'));
      var list = cities[province] || [];
      var found = false;
      list.forEach(function (name) {
        if (name === previous) found = true;
        citySelect.appendChild(option(name, name));
      });
      if (previous && !found) {
        // رکوردِ قدیمی با شهری بیرون از فهرست: نمایش می‌دهیم تا ادمین ببیند.
        citySelect.appendChild(option(previous, previous + ' (خارج از فهرستِ رسمی)'));
      }
      citySelect.value = previous || '';
      rebuildLocalities(province);
    }

    function rebuildLocalities(province) {
      if (!localityInput) return;
      var listId = 'kw-locality-options';
      var list = document.getElementById(listId);
      if (!list) {
        list = document.createElement('datalist');
        list.id = listId;
        localityInput.setAttribute('list', listId);
        localityInput.parentNode.appendChild(list);
      }
      list.innerHTML = '';
      var items = localities[province] || [];
      items.forEach(function (name) {
        list.appendChild(option(name, name));
      });
      localityInput.placeholder = items.length
        ? 'اختیاری — از فهرست یا تایپِ نامِ روستا'
        : 'اختیاری — مثلاً «روستای قلعه‌نو»';
    }

    provinceSelect.addEventListener('change', function () {
      rebuildCities('');
    });

    rebuildCities(citySelect.value);
  });
})();
