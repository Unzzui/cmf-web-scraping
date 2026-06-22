(function(){
  const ROLE_TITLES = {
    "210000": "Estado de situación financiera, corriente/no corriente - Estados financieros consolidados",
    "310000": "Estado del resultado, por función de gasto – Estados financieros consolidados",
    "510000": "Estado de flujos de efectivo, método directo – Estados financieros consolidados",
  };
  const ROLE_ORDER = ["210000","310000","510000"];

  // Plantilla base: estructura más usada para iniciar nuevas empresas
  const DEFAULT_TEMPLATE = {
    "210000": [
      "Activos [sinopsis]",
      "Activos corrientes [sinopsis]",
      "Efectivo y equivalentes al efectivo",
      "Otros activos financieros corrientes",
      "Otros activos no financieros corrientes",
      "Deudores comerciales y otras cuentas por cobrar corrientes",
      "Inventarios corrientes",
      "Activos no corrientes [sinopsis]",
      "Propiedades, planta y equipo",
      "Activos intangibles",
      "Inversiones contabilizadas mediante el método de la participación",
      "Activos por impuestos diferidos",
      "Pasivos [sinopsis]",
      "Pasivos corrientes [sinopsis]",
      "Cuentas por pagar comerciales y otras cuentas por pagar corrientes",
      "Obligaciones financieras corrientes",
      "Pasivos no corrientes [sinopsis]",
      "Obligaciones financieras no corrientes",
      "Pasivos por impuestos diferidos",
      "Patrimonio [sinopsis]",
      "Patrimonio atribuible a los propietarios de la controladora",
      "Intereses no controladores",
      "Patrimonio total"
    ],
    "310000": [
      "Ingresos de actividades ordinarias",
      "Costo de ventas",
      "Resultado bruto",
      "Otros ingresos",
      "Gastos de ventas",
      "Gastos de administración",
      "Otros gastos",
      "Ingresos y gastos financieros [sinopsis]",
      "Ingresos financieros",
      "Gastos financieros",
      "Resultado antes de impuestos",
      "Impuesto a las ganancias",
      "Resultado del ejercicio"
    ],
    "510000": [
      "Flujos de efectivo de actividades de operación [sinopsis]",
      "Cobros procedentes de las ventas de bienes y prestación de servicios",
      "Pagos a proveedores por suministros de bienes y servicios",
      "Pagos a y por cuenta de los empleados",
      "Intereses pagados",
      "Intereses recibidos",
      "Impuestos a las ganancias pagados",
      "Flujos netos de efectivo procedentes de actividades de operación",
      "Flujos de efectivo de actividades de inversión [sinopsis]",
      "Compras de propiedades, planta y equipo",
      "Ventas de propiedades, planta y equipo",
      "Adquisición de subsidiarias",
      "Flujos netos de efectivo procedentes de actividades de inversión",
      "Flujos de efectivo de actividades de financiación [sinopsis]",
      "Préstamos recibidos",
      "Pago de préstamos",
      "Dividendos pagados",
      "Flujos netos de efectivo procedentes de actividades de financiación",
      "Aumento (disminución) neto de efectivo y equivalentes",
      "Efectivo y equivalentes al efectivo al final del periodo"
    ]
  };

  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  const state = {
    path: 'estructura_eeff_empresas.json',
    data: { version: 1, empresas: [] },
    filtered: null,
    selectedIndex: -1,
    activeRole: '210000',
    dirty: false,
    serverMode: false, // true si /api/estructura está disponible
    saveTimer: null,
    fileHandle: null,
    focusLineIndex: null,
    empresasFaltantes: [], // Empresas del XBRL que no están en el JSON
    empresasXBRL: [], // Todas las empresas del directorio XBRL
  };

  function setStatus(msg){
    const el = $('#status');
    el.textContent = msg || '';
    if(msg){
      setTimeout(()=>{ if($('#status').textContent === msg) $('#status').textContent = ''; }, 4000);
    }
  }

  function markDirty(){
    state.dirty = true;
    setStatus('Cambios sin guardar');
    window.onbeforeunload = () => 'Tiene cambios sin guardar.';
    scheduleAutoSave();
  }

  function clearDirty(){
    state.dirty = false;
    setStatus('');
    window.onbeforeunload = null;
  }

  function setAutosaveStatus(text, ok=false){
    const el = $('#autosave');
    if(!el) return;
    el.textContent = `Auto-guardado: ${text}`;
    el.style.color = ok ? '#86efac' : '';
  }

  function scheduleAutoSave(){
    if(state.saveTimer) clearTimeout(state.saveTimer);
    const fn = state.serverMode ? saveToServer : (state.fileHandle ? saveToBoundFile : null);
    if(!fn) return;
    state.saveTimer = setTimeout(fn, 150);
  }

  async function ensureRWPermission(handle){
    if(!handle) return false;
    if(handle.queryPermission){
      const q = await handle.queryPermission({mode: 'readwrite'});
      if(q === 'granted') return true;
    }
    if(handle.requestPermission){
      const r = await handle.requestPermission({mode: 'readwrite'});
      return r === 'granted';
    }
    return false;
  }

  async function saveToBoundFile(){
    try{
      if(!state.fileHandle) return;
      const ok = await ensureRWPermission(state.fileHandle);
      if(!ok){ setAutosaveStatus('permiso denegado'); return; }
      // Normalizar antes de escribir
      (state.data.empresas||[]).forEach(e => ensureRoles(e));
      const writable = await state.fileHandle.createWritable();
      await writable.write(new Blob([JSON.stringify(state.data, null, 2)], {type:'application/json;charset=utf-8'}));
      await writable.close();
      setAutosaveStatus('guardado', true);
      state.dirty = false;
      window.onbeforeunload = null;
    }catch(err){
      console.error('Error guardando:', err);
      setAutosaveStatus('error al guardar');
    }
  }

  async function saveToServer(){
    try{
      // Normalizar antes de enviar
      (state.data.empresas||[]).forEach(e => ensureRoles(e));
      const res = await fetch('/api/estructura', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state.data),
      });
      if(!res.ok){
        setAutosaveStatus('error ('+res.status+')');
        return;
      }
      setAutosaveStatus('guardado', true);
      state.dirty = false;
      window.onbeforeunload = null;
    }catch(err){
      console.error('Error guardando en servidor:', err);
      setAutosaveStatus('error servidor');
    }
  }

  async function bindFile(){
    if(!window.showOpenFilePicker){
      alert('Tu navegador no soporta escritura directa al archivo. Usa "Guardar (descargar)".');
      return;
    }
    try{
      const [handle] = await window.showOpenFilePicker({
        multiple: false,
        types: [{description: 'JSON', accept: {'application/json': ['.json']}}],
        excludeAcceptAllOption: false,
      });
      if(!handle) return;
      const ok = await ensureRWPermission(handle);
      if(!ok){
        alert('Se requiere permiso de lectura/escritura para auto-guardar.');
        return;
      }
      state.fileHandle = handle;
      setAutosaveStatus('activo', true);
      // Intentar leer desde el archivo vinculado para sincronizar
      try{
        const f = await handle.getFile();
        const text = await f.text();
        const data = JSON.parse(text);
        if(data && Array.isArray(data.empresas)){
          data.empresas.forEach(ensureRoles);
          state.data = data;
          state.selectedIndex = data.empresas.length ? 0 : -1;
          renderEmpresaList();
          renderEditor();
          setStatus('Sincronizado desde archivo vinculado');
        }
      }catch(e){ /* leer es opcional */ }
      // Guardar inmediatamente el estado actual
      scheduleAutoSave();
    }catch(err){
      if(err && err.name === 'AbortError') return; // cancelado
      console.error(err);
      alert('No se pudo vincular el archivo: '+err);
    }
  }

  function ensureRoles(emp){
    const roles = Array.isArray(emp.roles) ? emp.roles : [];
    const byId = Object.fromEntries(roles.map(r => [r.id, r]));
    emp.roles = ROLE_ORDER.map(id => {
      const existing = byId[id] || { id, titulo: ROLE_TITLES[id], lineas: [] };
      if(!existing.titulo) existing.titulo = ROLE_TITLES[id];
      if(!Array.isArray(existing.lineas)) existing.lineas = [];
      return existing;
    });
  }

  function getEmpresas(){
    return state.data.empresas || [];
  }

  function setEmpresas(arr){
    state.data.empresas = arr;
  }

  function filteredEmpresas(){
    const q = ($('#search')?.value || '').toLowerCase().trim();
    const arr = getEmpresas();
    if(!q) return arr.map((e,i)=>({emp:e, idx:i}));
    return arr.map((e,i)=>({emp:e, idx:i}))
      .filter(({emp}) => {
        const rut = emp.empresa?.rut || '';
        const nom = emp.empresa?.nombre || '';
        return rut.toLowerCase().includes(q) || nom.toLowerCase().includes(q);
      });
  }

  function renderEmpresaList(){
    const list = $('#empresaList');
    list.innerHTML = '';
    const items = filteredEmpresas();
    items.forEach(({emp, idx}) => {
      const li = document.createElement('li');
      li.className = 'empresa-item' + (idx === state.selectedIndex ? ' active' : '');
      li.innerHTML = `<strong>${escapeHtml(emp.empresa?.rut || '(sin RUT)')}</strong><br/>`+
        `<small>${escapeHtml(emp.empresa?.nombre || '(sin nombre)')} — lang=${escapeHtml(emp.lang || 'es')}</small>`;
      li.addEventListener('click', () => {
        state.selectedIndex = idx;
        renderEmpresaList();
        renderEditor();
      });
      list.appendChild(li);
    });
  }

  function renderEditor(){
    const container = $('#content');
    container.innerHTML = '';
    if(state.selectedIndex < 0 || state.selectedIndex >= getEmpresas().length){
      const d = document.createElement('div');
      d.className = 'placeholder';
      d.innerHTML = '<h2>No hay empresa seleccionada</h2><p>Elige una empresa en la izquierda, o crea una nueva.</p>';
      container.appendChild(d);
      return;
    }
    const emp = getEmpresas()[state.selectedIndex];
    ensureRoles(emp);

    const cardInfo = document.createElement('div');
    cardInfo.className = 'card';
    cardInfo.innerHTML = `
      <h2>Datos de la empresa</h2>
      <div class="grid cols-2">
        <div>
          <label>RUT</label>
          <input type="text" id="f_rut" value="${escapeAttr(emp.empresa?.rut || '')}">
        </div>
        <div>
          <label>Nombre</label>
          <input type="text" id="f_nombre" value="${escapeAttr(emp.empresa?.nombre || '')}">
        </div>
        <div>
          <label>Idioma</label>
          <select id="f_lang">
            <option value="es" ${emp.lang==='es'?'selected':''}>Español</option>
            <option value="en" ${emp.lang==='en'?'selected':''}>Inglés</option>
          </select>
        </div>
      </div>
      <div class="actions" style="margin-top:10px">
        <button class="btn" id="btnDeleteEmp">Eliminar empresa</button>
      </div>
    `;
    container.appendChild(cardInfo);

    $('#f_rut').addEventListener('input', e => { emp.empresa = emp.empresa||{}; emp.empresa.rut = e.target.value; markDirty(); renderEmpresaList(); });
    $('#f_nombre').addEventListener('input', e => { emp.empresa = emp.empresa||{}; emp.empresa.nombre = e.target.value; markDirty(); renderEmpresaList(); });
    $('#f_lang').addEventListener('change', e => { emp.lang = e.target.value; markDirty(); renderEmpresaList(); });
    const btnDeleteEmp = $('#btnDeleteEmp');
    if(btnDeleteEmp) {
      console.log('Agregando event listener al botón eliminar empresa');
      btnDeleteEmp.addEventListener('click', () => {
        console.log('Función eliminar empresa llamada - mostrando modal');
        showModalEliminar(state.selectedIndex);
      });
    } else {
      console.error('No se encontró el botón btnDeleteEmp');
    }

    // Roles
    const cardRoles = document.createElement('div');
    cardRoles.className = 'card';
    const tabs = document.createElement('div');
    tabs.className = 'tabs';
    emp.roles.forEach(r => {
      const t = document.createElement('button');
      t.className = 'tab' + (state.activeRole === r.id ? ' active' : '');
      t.textContent = `[${r.id}] ${r.titulo||''}`;
      t.setAttribute('data-count', r.lineas?.length || 0);
      t.addEventListener('click', () => { state.activeRole = r.id; renderEditor(); });
      tabs.appendChild(t);
    });
    cardRoles.appendChild(tabs);

    const active = emp.roles.find(r => r.id === state.activeRole) || emp.roles[0];
    if(active){
      const roleBox = document.createElement('div');
      roleBox.className = 'line-editor';
      roleBox.innerHTML = `
        <div class="grid cols-2">
          <div>
            <label>Título del rol</label>
            <input type="text" id="roleTitle" value="${escapeAttr(active.titulo||'')}">
          </div>
          <div style="display:flex; align-items:flex-end; gap:8px">
            <span class="chip">${active.id}</span>
          </div>
        </div>
        <div class="quick-add">
          <input type="text" id="addLineText" placeholder="Escribe una línea y pulsa Enter…" />
          <button class="btn primary" id="btnAddLine">+ Agregar línea</button>
          <button class="btn" id="btnAddSinopsis">+ Categoría [sinopsis]</button>
        </div>
        <div class="bulk-paste" style="margin-top: 10px; padding: 10px; border: 2px dashed #ccc; border-radius: 8px;">
          <div style="margin-bottom: 8px;">
            <strong>📋 Pegado Masivo</strong> - Copia todas las líneas de la CMF y pégalas aquí:
          </div>
          <textarea id="bulkPasteText" placeholder="Pega aquí todas las líneas del balance/estado de resultados/flujo desde la CMF...&#10;Ejemplo:&#10;Activos [sinopsis]&#10;Activos corrientes [sinopsis]&#10;Efectivo y equivalentes al efectivo&#10;..." style="width: 100%; height: 120px; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; font-size: 12px;"></textarea>
          <div style="margin-top: 8px;">
            <button class="btn primary" id="btnBulkPaste">🔄 Reemplazar todas las líneas</button>
            <button class="btn" id="btnBulkAdd">➕ Agregar al final</button>
            <span style="margin-left: 10px; font-size: 12px; color: #666;">
              Tip: Ctrl+A en la CMF, Ctrl+C, pegar aquí y clickear "Reemplazar"
            </span>
          </div>
        </div>
        <ul class="line-list" id="lineList"></ul>
      `;
      cardRoles.appendChild(roleBox);
      container.appendChild(cardRoles);

      $('#roleTitle').addEventListener('input', e => { active.titulo = e.target.value; markDirty(); renderEditor(); });
      const addLineNow = () => {
        const inp = $('#addLineText');
        const val = (inp?.value || '').trim();
        if(val){
          active.lineas.push(val);
          inp.value = '';
        } else {
          active.lineas.push('Nueva línea');
        }
        markDirty();
        renderEditor();
      };
      $('#btnAddLine').addEventListener('click', addLineNow);
      $('#addLineText').addEventListener('keydown', (e)=>{
        if(e.key === 'Enter'){
          e.preventDefault();
          addLineNow();
        }
      });
      $('#btnAddSinopsis').addEventListener('click', () => { active.lineas.push('Nueva categoría [sinopsis]'); markDirty(); renderEditor(); });
      
      // Pegado masivo - reemplazar todas las líneas
      $('#btnBulkPaste').addEventListener('click', () => {
        const textarea = $('#bulkPasteText');
        if(!textarea || !textarea.value.trim()) {
          showShortcutFeedback('❌ Pega primero las líneas en el área de texto', 'error');
          return;
        }
        
        const lines = processAccountLines(textarea.value);
          
        if(lines.length === 0) {
          showShortcutFeedback('❌ No hay líneas válidas para pegar', 'error');
          return;
        }
        
        // Reemplazar completamente las líneas del rol activo
        active.lineas = lines;
        markDirty();
        updateLinesOnly(active, true);
        showShortcutFeedback(`✅ ${lines.length} líneas reemplazadas en ${active.titulo}`);
        textarea.value = ''; // Limpiar textarea
      });
      
      // Pegado masivo - agregar al final
      $('#btnBulkAdd').addEventListener('click', () => {
        const textarea = $('#bulkPasteText');
        if(!textarea || !textarea.value.trim()) {
          showShortcutFeedback('❌ Pega primero las líneas en el área de texto', 'error');
          return;
        }
        
        const lines = processAccountLines(textarea.value);
          
        if(lines.length === 0) {
          showShortcutFeedback('❌ No hay líneas válidas para agregar', 'error');
          return;
        }
        
        // Agregar las líneas al final del rol activo
        active.lineas.push(...lines);
        markDirty();
        updateLinesOnly(active, true);
        showShortcutFeedback(`✅ ${lines.length} líneas agregadas al final de ${active.titulo}`);
        textarea.value = ''; // Limpiar textarea
      });

      renderLines(active);
      // Autofocus en el input de agregado rápido solo si no hay una línea específica que enfocar
      setTimeout(()=>{ 
        if(state.focusLineIndex === null) {
          const el = $('#addLineText'); 
          if(el) el.focus(); 
        }
      }, 0);
    }
  }

  function processAccountLines(rawText) {
    // Procesar texto de la CMF para extraer solo los nombres de cuentas
    return rawText.trim().split('\n')
      .map(line => line.trim())
      .filter(line => {
        // Filtrar líneas vacías
        if (line.length === 0) return false;
        
        // Filtrar líneas que son solo números (con puntos, comas, guiones)
        if (/^[\d\.,\-\s]+$/.test(line)) return false;
        
        // Filtrar líneas que empiezan con números seguidos de espacios (datos numéricos)
        if (/^\s*[\d\.,\-]+\s*$/.test(line)) return false;
        
        return true;
      })
      .map(line => {
        // Limpiar la línea: quitar números al final y espacios extra
        let cleaned = line;
        
        // Si la línea termina con números separados por espacios/tabs, quitarlos
        // Ejemplo: "Ingresos de actividades ordinarias    8.202.925.856    4.171.342.709"
        cleaned = cleaned.replace(/\s+[\d\.,\-]+(\s+[\d\.,\-]+)*\s*$/g, '');
        
        // Quitar espacios múltiples
        cleaned = cleaned.replace(/\s+/g, ' ').trim();
        
        return cleaned;
      })
      .filter(line => {
        // Segundo filtro después de limpiar
        if (line.length === 0) return false;
        
        // Verificar que no sea solo números después de limpiar
        if (/^[\d\.,\-\s]+$/.test(line)) return false;
        
        // Verificar que tenga al menos algunas letras
        if (!/[a-zA-ZáéíóúÁÉÍÓÚñÑ]/.test(line)) return false;
        
        // Filtrar líneas muy cortas que probablemente no sean nombres de cuentas
        if (line.length < 3) return false;
        
        return true;
      });
  }

  function updateLinesOnly(role, preserveScroll = false) {
    // Función para actualizar solo las líneas sin re-renderizar todo el editor
    // Preserva la posición de scroll si se especifica
    let scrollPosition = null;
    if (preserveScroll) {
      scrollPosition = {
        top: window.pageYOffset || document.documentElement.scrollTop,
        left: window.pageXOffset || document.documentElement.scrollLeft
      };
    }
    
    renderLines(role);
    
    if (preserveScroll && scrollPosition) {
      // Restaurar posición de scroll después del render
      setTimeout(() => {
        window.scrollTo(scrollPosition.left, scrollPosition.top);
      }, 0);
    }
  }

  function renderLines(role){
    const ul = $('#lineList');
    ul.innerHTML = '';
    role.lineas.forEach((text, idx) => {
      const li = document.createElement('li');
      li.className = 'line-item';
      li.draggable = true;
      li.dataset.idx = String(idx);
      li.innerHTML = `
        <div class="handle" title="Arrastra para reordenar">☰</div>
        <input type="text" value="${escapeAttr(text)}" />
        <div class="line-actions">
          <button class="icon-btn" data-act="sinopsis" title="Alternar [sinopsis]">[sinopsis]</button>
          <button class="icon-btn" data-act="insertar" title="Insertar debajo">+ debajo</button>
          <button class="icon-btn icon-danger" data-act="eliminar" title="Eliminar">✕</button>
        </div>
      `;
      const input = $('input', li);
      input.addEventListener('input', (e)=>{
        role.lineas[idx] = e.target.value;
        markDirty();
        
        // Autocompletado solo si el usuario ha escrito suficiente
        if(e.target.value.trim().length >= 3) {
          const suggestions = getSuggestionsForInput(e.target.value, role.id);
          if(suggestions.length > 0) {
            showAutocompleteSuggestions(input, suggestions);
          } else {
            hideAutocompleteSuggestions();
          }
        } else {
          hideAutocompleteSuggestions();
        }
      });
      input.addEventListener('focus', ()=>{ 
        li.classList.add('selected');
        // No mostrar autocomplete automáticamente al hacer focus
      });
      input.addEventListener('blur', ()=>{ 
        li.classList.remove('selected');
        // Ocultar autocompletado inmediatamente al perder focus
        hideAutocompleteSuggestions();
      });
      input.addEventListener('keydown', (e)=>{
        // Manejar autocompletado primero
        if(handleAutocompleteNavigation(e, input)) {
          return; // Autocompletado manejó el evento
        }
        
        // Los shortcuts de movimiento ahora se manejan en handleInputShortcuts
        // que se llama desde el event listener global
      });
      $('.line-actions', li).addEventListener('click', (e)=>{
        const btn = e.target.closest('button');
        if(!btn) return;
        const act = btn.dataset.act;
        if(act === 'eliminar'){
          role.lineas.splice(idx,1);
        } else if(act === 'insertar'){
          role.lineas.splice(idx+1,0,'Nueva línea');
        } else if(act === 'sinopsis'){
          const has = /\[\s*sinopsis\s*\]$/i.test(role.lineas[idx]);
          role.lineas[idx] = has ? role.lineas[idx].replace(/\s*\[\s*sinopsis\s*\]$/i,'') : (role.lineas[idx].trim() + ' [sinopsis]');
        }
        markDirty();
        renderEditor();
      });
      // Drag and drop events mejorado
      li.addEventListener('dragstart', (e)=>{
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(idx));
        li.classList.add('dragging');
        // Guardar el estado inicial para mejor animación
        li.style.opacity = '0.5';
        showShortcutFeedback('Arrastrando línea...');
      });
      
      li.addEventListener('dragend', ()=> {
        li.classList.remove('dragging');
        li.style.opacity = '';
      });
      
      li.addEventListener('dragover', (e)=>{
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        // Agregar indicador visual de drop zone
        li.classList.add('drag-over');
      });
      
      li.addEventListener('dragleave', (e)=>{
        // Solo remover si realmente salimos del elemento
        if(!li.contains(e.relatedTarget)) {
          li.classList.remove('drag-over');
        }
      });
      
      li.addEventListener('drop', (e)=>{
        e.preventDefault();
        li.classList.remove('drag-over');
        
        const from = parseInt(e.dataTransfer.getData('text/plain'), 10);
        const to = idx;
        
        if(isFinite(from) && isFinite(to) && from !== to){
          // Smooth reordering
          const item = role.lineas.splice(from,1)[0];
          role.lineas.splice(to,0,item);
          
          // Focus en la línea movida
          state.focusLineIndex = to;
          
          markDirty();
          renderEditor();
          showShortcutFeedback(`Línea movida a posición ${to + 1}`);
        }
      });
      ul.appendChild(li);
    });
    if(state.focusLineIndex !== null){
      const i = state.focusLineIndex; 
      state.focusLineIndex = null;
      // Usar setTimeout para asegurar que el DOM esté actualizado y evitar conflictos con otros focus
      setTimeout(() => {
        const inputs = $$('#lineList input');
        if(inputs[i]){ 
          // Guardar la posición de scroll actual antes de hacer focus
          const currentScrollTop = window.pageYOffset || document.documentElement.scrollTop;
          
          inputs[i].focus(); 
          const v = inputs[i].value; 
          inputs[i].setSelectionRange(v.length, v.length);
          
          // Usar un setTimeout adicional para el scroll después del focus
          setTimeout(() => {
            // Mantener la vista centrada en la línea enfocada, pero de forma más suave
            inputs[i].scrollIntoView({ 
              behavior: 'auto', // Cambiar a 'auto' para scroll inmediato
              block: 'nearest', // Usar 'nearest' en lugar de 'center' para menos movimiento
              inline: 'nearest'
            });
          }, 5);
        }
      }, 10);
    }
  }

  // I/O
  async function loadFromServer(){
    // intento 1: API del servidor
    try{
      const api = '/api/estructura';
      const res = await fetch(api, { cache: 'no-store' });
      if(res.ok){
        const data = await res.json();
        if(data && Array.isArray(data.empresas)){
          data.empresas.forEach(ensureRoles);
          state.data = data;
          state.selectedIndex = data.empresas.length ? 0 : -1;
          state.serverMode = true;
          clearDirty();
          renderEmpresaList();
          renderEditor();
          setAutosaveStatus('servidor activo', true);
          setStatus('Cargado desde API');
          // Cargar empresas XBRL en paralelo
          loadEmpresasXBRL();
          return;
        }
      }
    }catch(_){}

    // intento 2: archivo estático relativo
    try{
      const res = await fetch(state.path, { cache: 'no-store' });
      if(!res.ok) throw new Error('HTTP '+res.status);
      const data = await res.json();
      if(!data || !Array.isArray(data.empresas)) throw new Error('Formato inválido: falta empresas[]');
      data.empresas.forEach(ensureRoles);
      state.data = data;
      state.selectedIndex = data.empresas.length ? 0 : -1;
      clearDirty();
      renderEmpresaList();
      renderEditor();
      setStatus('Cargado desde archivo');
      
      // Intentar cargar empresas XBRL también si hay servidor
      try{
        await loadEmpresasXBRL();
      }catch(e){
        console.warn('No se pudo cargar empresas XBRL desde archivo estático:', e);
      }
    }catch(err){
      alert('No se pudo cargar. Sirve esta carpeta por HTTP o usa el servidor incluido.\n\nDetalle: '+err);
    }
  }

  async function loadEmpresasXBRL(){
    // Intentar detectar si hay servidor disponible
    if(!state.serverMode) {
      try {
        const testRes = await fetch('/api/empresas-xbrl', { cache: 'no-store' });
        if(testRes.ok) {
          state.serverMode = true; // Servidor detectado
        } else {
          return; // No hay servidor
        }
      } catch(e) {
        return; // No hay servidor
      }
    }
    
    try{
      // Agregar timestamp para evitar cache del navegador
      const timestamp = Date.now();
      
      // Cargar empresas faltantes con cache-busting
      const resFaltantes = await fetch(`/api/empresas-faltantes?t=${timestamp}`, { 
        cache: 'no-store',
        headers: {
          'Cache-Control': 'no-cache, no-store, must-revalidate',
          'Pragma': 'no-cache'
        }
      });
      if(resFaltantes.ok){
        const data = await resFaltantes.json();
        state.empresasFaltantes = data.faltantes || [];
      }
      
      // Cargar todas las empresas XBRL con cache-busting
      const resXBRL = await fetch(`/api/empresas-xbrl?t=${timestamp}`, { 
        cache: 'no-store',
        headers: {
          'Cache-Control': 'no-cache, no-store, must-revalidate',
          'Pragma': 'no-cache'
        }
      });
      if(resXBRL.ok){
        const data = await resXBRL.json();
        state.empresasXBRL = data.empresas || [];
      }
      
      // Actualizar UI
      updateMissingCompaniesIndicator();
      
    }catch(err){
      console.warn('No se pudieron cargar empresas XBRL:', err);
    }
  }

  function updateMissingCompaniesIndicator(){
    // Actualizar indicador en la sidebar
    updateSidebarIndicator();
    // Actualizar botón agregar empresa si es necesario
    updateAddButtonIndicator();
  }

  function updateSidebarIndicator(){
    const sidebar = $('.sidebar-header');
    if(!sidebar) return;
    
    // Buscar indicador existente o crear uno nuevo
    let indicator = sidebar.querySelector('.missing-companies-indicator');
    if(!indicator){
      indicator = document.createElement('div');
      indicator.className = 'missing-companies-indicator';
      sidebar.appendChild(indicator);
    }
    
    const faltantes = state.empresasFaltantes.length;
    const total = state.empresasXBRL.length;
    
    if(faltantes === 0 && total > 0){
      indicator.innerHTML = `
        <div class="indicator-complete">
          ✅ Todas las empresas XBRL agregadas (${total})
        </div>
      `;
    } else if(total === 0) {
      indicator.innerHTML = `
        <div class="indicator-missing">
          ⚠️ No se pudieron cargar empresas XBRL
        </div>
      `;
    } else {
      indicator.innerHTML = `
        <div class="indicator-missing">
          ⚠️ <strong>${faltantes}</strong> de ${total} empresas XBRL sin agregar
          <button class="btn-link" id="btnShowMissing">Ver lista</button>
        </div>
      `;
      
      const btnShow = indicator.querySelector('#btnShowMissing');
      if(btnShow){
        btnShow.addEventListener('click', showMissingCompaniesList);
      }
    }
  }

  function updateAddButtonIndicator(){
    const btnAdd = $('#btnAddEmpresa');
    if(!btnAdd) return;
    
    const faltantes = state.empresasFaltantes.length;
    if(faltantes > 0){
      btnAdd.setAttribute('data-missing-count', faltantes);
    } else {
      btnAdd.removeAttribute('data-missing-count');
    }
  }

  function showMissingCompaniesList(){
    if(state.empresasFaltantes.length === 0) return;
    
    const modal = document.createElement('div');
    modal.className = 'modal show';
    modal.innerHTML = `
      <div class="modal-content" style="max-width: 800px;">
        <div class="modal-header">
          <h3>Empresas XBRL sin agregar (${state.empresasFaltantes.length})</h3>
          <button class="modal-close" onclick="this.closest('.modal').remove()">&times;</button>
        </div>
        <div class="modal-body">
          <div class="missing-companies-list">
            ${state.empresasFaltantes.map(emp => `
              <div class="missing-company-item">
                <div class="company-info">
                  <strong>${escapeHtml(emp.rut)}</strong>
                  <span>${escapeHtml(emp.nombre)}</span>
                </div>
                <button class="btn primary btn-sm" onclick="window.addCompanyFromXBRL('${escapeAttr(emp.rut)}', '${escapeAttr(emp.nombre)}')">
                  Agregar
                </button>
              </div>
            `).join('')}
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn" onclick="this.closest('.modal').remove()">Cerrar</button>
        </div>
      </div>
    `;
    
    document.body.appendChild(modal);
  }

  function importFromFile(file){
    const reader = new FileReader();
    reader.onload = () => {
      try{
        const data = JSON.parse(reader.result);
        if(!data || !Array.isArray(data.empresas)) throw new Error('Formato inválido: falta empresas[]');
        data.empresas.forEach(ensureRoles);
        state.data = data;
        state.selectedIndex = data.empresas.length ? 0 : -1;
        renderEmpresaList();
        renderEditor();
        markDirty();
        setStatus('Archivo importado');
      }catch(err){
        alert('JSON inválido: '+err);
      }
    };
    reader.readAsText(file, 'utf-8');
  }

  function exportToFile(){
    // Normalización mínima antes de guardar
    (state.data.empresas||[]).forEach(e => ensureRoles(e));
    const blob = new Blob([JSON.stringify(state.data, null, 2)], {type:'application/json;charset=utf-8'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'estructura_eeff_empresas.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(()=>URL.revokeObjectURL(a.href), 1000);
    clearDirty();
    setStatus('Descargado');
  }

  async function copyJson(){
    try{
      await navigator.clipboard.writeText(JSON.stringify(state.data, null, 2));
      setStatus('JSON copiado al portapapeles');
    }catch(err){
      alert('No se pudo copiar: '+err);
    }
  }

  async function addEmpresa(){
    console.log('Función addEmpresa llamada - mostrando modal');
    await showModalAgregarEmpresa();
  }

  async function showModalAgregarEmpresa(){
    const modal = $('#modalAgregarEmpresa');
    if(!modal) return;
    
    // Limpiar formulario
    $('#modalRut').value = '';
    $('#modalNombre').value = '';
    $('#modalIdioma').value = 'es';
    $('#modalPlantilla').checked = true;
    
    // Mostrar modal primero
    modal.classList.add('show');
    
    // Mostrar sugerencias XBRL si hay empresas faltantes (async)
    await updateModalSuggestions();
    
    // Focus en el primer input
    setTimeout(() => $('#modalRut').focus(), 100);
  }

  async function updateModalSuggestions(){
    const suggestionsContainer = $('#xbrlSuggestions');
    const suggestionsList = $('#suggestionsList');
    
    if(!suggestionsContainer || !suggestionsList) return;
    
    // Refrescar lista de empresas faltantes si está en modo servidor
    if(state.serverMode){
      await loadEmpresasXBRL();
    }
    
    if(state.empresasFaltantes.length === 0){
      suggestionsContainer.style.display = 'none';
      return;
    }
    
    // Mostrar las primeras 5 empresas faltantes
    const toShow = state.empresasFaltantes.slice(0, 5);
    suggestionsList.innerHTML = toShow.map(emp => `
      <div class="suggestion-item" onclick="selectXBRLSuggestion('${escapeAttr(emp.rut)}', '${escapeAttr(emp.nombre)}')">
        <strong>${escapeHtml(emp.rut)}</strong>
        <span>${escapeHtml(emp.nombre)}</span>
      </div>
    `).join('');
    
    if(state.empresasFaltantes.length > 5){
      suggestionsList.innerHTML += `
        <div class="suggestion-more">
          ... y ${state.empresasFaltantes.length - 5} empresas más
          <button class="btn-link" onclick="showMissingCompaniesList()">Ver todas</button>
        </div>
      `;
    }
    
    suggestionsContainer.style.display = 'block';
  }

  // Función global para seleccionar sugerencia
  window.selectXBRLSuggestion = function(rut, nombre) {
    const rutInput = $('#modalRut');
    const nombreInput = $('#modalNombre');
    if(rutInput) rutInput.value = rut;
    if(nombreInput) nombreInput.value = nombre;
    
    // Ocultar sugerencias
    const suggestionsContainer = $('#xbrlSuggestions');
    if(suggestionsContainer) suggestionsContainer.style.display = 'none';
  };

  function hideModalAgregarEmpresa(){
    const modal = $('#modalAgregarEmpresa');
    if(modal) modal.classList.remove('show');
  }

  async function confirmarAgregarEmpresa(){
    console.log('Confirmando agregar empresa...');
    
    const rut = $('#modalRut').value?.trim();
    const nombre = $('#modalNombre').value?.trim() || '';
    const lang = $('#modalIdioma').value || 'es';
    const useTpl = $('#modalPlantilla').checked;
    
    console.log('Datos del formulario:', { rut, nombre, lang, useTpl });
    
    if(!rut) {
      alert('Debe ingresar un RUT para la empresa');
      $('#modalRut').focus();
      return;
    }
    
    // Verificar que el RUT no exista ya
    const existingEmpresas = getEmpresas();
    console.log('Empresas existentes:', existingEmpresas.length);
    if(existingEmpresas.some(e => e.empresa?.rut === rut)){
      alert('Ya existe una empresa con este RUT');
      $('#modalRut').focus();
      return;
    }
    
    const emp = { empresa: { rut, nombre }, lang, roles: [] };
    console.log('Empresa creada:', emp);
    
    if(useTpl){
      emp.roles = ROLE_ORDER.map(id => ({ id, titulo: ROLE_TITLES[id], lineas: [...(DEFAULT_TEMPLATE[id]||[])] }));
    } else {
      ensureRoles(emp);
    }
    
    console.log('Agregando empresa al array...');
    const arr = getEmpresas();
    arr.push(emp);
    setEmpresas(arr);
    state.selectedIndex = arr.length - 1;
    const s = document.querySelector('#search'); if(s){ s.value=''; }
    
    console.log('Marcando como dirty...');
    markDirty();
    console.log('Renderizando lista...');
    renderEmpresaList();
    console.log('Renderizando editor...');
    renderEditor();
    console.log('Empresa agregada exitosamente');
    setStatus('Empresa agregada correctamente');
    showShortcutFeedback('✅ Empresa agregada exitosamente', 'success');
    
    hideModalAgregarEmpresa();
    
    // Esperar a que se guarde y luego actualizar empresas faltantes
    if(state.serverMode){
      // Esperar un breve momento para que el auto-guardado se complete
      setTimeout(async () => {
        await loadEmpresasXBRL();
        updateStatusInRealTime();
      }, 500); // Dar tiempo para que el auto-guardado termine
    } else {
      // Actualizar estado visual en tiempo real si no está en modo servidor
      setTimeout(() => updateStatusInRealTime(), 100);
    }
  }

  function showModalEliminar(empresaIndex) {
    const modal = $('#modalEliminar');
    if(!modal) return;
    
    const emp = getEmpresas()[empresaIndex];
    const rutNombre = emp?.empresa?.rut || '(sin RUT)';
    const nombre = emp?.empresa?.nombre || '(sin nombre)';
    
    const texto = $('#modalEliminarTexto');
    if(texto) {
      texto.innerHTML = `¿Está seguro de que desea eliminar la empresa <strong>${escapeHtml(rutNombre)} - ${escapeHtml(nombre)}</strong>?`;
    }
    
    // Guardar el índice para usar en la confirmación
    modal.dataset.empresaIndex = empresaIndex;
    
    // Mostrar modal
    modal.classList.add('show');
  }

  function hideModalEliminar() {
    const modal = $('#modalEliminar');
    if(modal) modal.classList.remove('show');
  }

  function confirmarEliminarEmpresa() {
    const modal = $('#modalEliminar');
    if(!modal) return;
    
    const empresaIndex = parseInt(modal.dataset.empresaIndex);
    if(!isFinite(empresaIndex)) return;
    
    console.log('Eliminando empresa en índice:', empresaIndex);
    
    const arr = getEmpresas();
    arr.splice(empresaIndex, 1);
    setEmpresas(arr);
    state.selectedIndex = -1;
    markDirty();
    renderEmpresaList();
    renderEditor();
    setStatus('Empresa eliminada correctamente');
    showShortcutFeedback('🗑️ Empresa eliminada correctamente', 'success');
    
    hideModalEliminar();
    
    // Esperar a que se guarde y luego actualizar empresas faltantes
    if(state.serverMode){
      // Esperar un breve momento para que el auto-guardado se complete
      setTimeout(async () => {
        await loadEmpresasXBRL();
        updateStatusInRealTime();
      }, 500); // Dar tiempo para que el auto-guardado termine
    } else {
      // Actualizar estado visual en tiempo real si no está en modo servidor
      setTimeout(() => updateStatusInRealTime(), 100);
    }
  }

  function attachGlobalHandlers(){
    const btnBind = $('#btnBind');
    if(btnBind) btnBind.addEventListener('click', bindFile);
    
    const btnLoad = $('#btnLoad');
    if(btnLoad) btnLoad.addEventListener('click', loadFromServer);
    
    const btnImport = $('#btnImport');
    const fileInput = $('#fileInput');
    if(btnImport && fileInput) {
      btnImport.addEventListener('click', ()=> fileInput.click());
      fileInput.addEventListener('change', (e)=>{ const f=e.target.files[0]; if(f) importFromFile(f); e.target.value=''; });
    }
    
    const btnExport = $('#btnExport');
    if(btnExport) btnExport.addEventListener('click', exportToFile);
    
    const btnCopy = $('#btnCopy');
    if(btnCopy) btnCopy.addEventListener('click', copyJson);
    
    const btnAddEmpresa = $('#btnAddEmpresa');
    if(btnAddEmpresa) {
      console.log('Agregando event listener al botón agregar empresa');
      btnAddEmpresa.addEventListener('click', async () => {
        await addEmpresa();
      });
    } else {
      console.error('No se encontró el botón btnAddEmpresa');
    }
    
    const search = $('#search');
    if(search) search.addEventListener('input', renderEmpresaList);
    
    // Event listeners para modal agregar empresa
    const modalAgregarClose = $('#modalAgregarClose');
    const modalAgregarCancel = $('#modalAgregarCancel');
    const modalAgregarConfirm = $('#modalAgregarConfirm');
    const modalAgregar = $('#modalAgregarEmpresa');
    
    if(modalAgregarClose) modalAgregarClose.addEventListener('click', hideModalAgregarEmpresa);
    if(modalAgregarCancel) modalAgregarCancel.addEventListener('click', hideModalAgregarEmpresa);
    if(modalAgregarConfirm) modalAgregarConfirm.addEventListener('click', async () => {
      await confirmarAgregarEmpresa();
    });
    
    // Cerrar modal al hacer click fuera
    if(modalAgregar) {
      modalAgregar.addEventListener('click', (e) => {
        if(e.target === modalAgregar) hideModalAgregarEmpresa();
      });
    }
    
    // Event listeners para modal eliminar empresa
    const modalEliminarClose = $('#modalEliminarClose');
    const modalEliminarCancel = $('#modalEliminarCancel');
    const modalEliminarConfirm = $('#modalEliminarConfirm');
    const modalEliminar = $('#modalEliminar');
    
    if(modalEliminarClose) modalEliminarClose.addEventListener('click', hideModalEliminar);
    if(modalEliminarCancel) modalEliminarCancel.addEventListener('click', hideModalEliminar);
    if(modalEliminarConfirm) modalEliminarConfirm.addEventListener('click', confirmarEliminarEmpresa);
    
    // Cerrar modal al hacer click fuera
    if(modalEliminar) {
      modalEliminar.addEventListener('click', (e) => {
        if(e.target === modalEliminar) hideModalEliminar();
      });
    }
    
    // Sistema de navegación por teclado y shortcuts
    document.addEventListener('keydown', (e) => {
      // Cerrar modales con Escape
      if(e.key === 'Escape') {
        const modalAgregar = $('#modalAgregarEmpresa');
        const modalEliminar = $('#modalEliminar');
        
        if(modalAgregar && modalAgregar.classList.contains('show')) {
          hideModalAgregarEmpresa();
          return;
        }
        if(modalEliminar && modalEliminar.classList.contains('show')) {
          hideModalEliminar();
          return;
        }
      }
      
      // Shortcuts globales (solo si no hay modal abierto)
      if(!isModalOpen()) {
        handleGlobalShortcuts(e);
      }
    });
  }

  function escapeHtml(s){
    return String(s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
  }
  function escapeAttr(s){
    return String(s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
  }

  function isModalOpen() {
    const modalAgregar = $('#modalAgregarEmpresa');
    const modalEliminar = $('#modalEliminar');
    return (modalAgregar && modalAgregar.classList.contains('show')) ||
           (modalEliminar && modalEliminar.classList.contains('show'));
  }

  function handleGlobalShortcuts(e) {
    // Evitar shortcuts si estamos escribiendo en un input/textarea
    const activeElement = document.activeElement;
    const isInInput = activeElement && (
      activeElement.tagName === 'INPUT' || 
      activeElement.tagName === 'TEXTAREA' || 
      activeElement.contentEditable === 'true'
    );

    if(isInInput) {
      // Solo permitir algunos shortcuts específicos dentro de inputs
      handleInputShortcuts(e);
      return;
    }

    // Shortcuts globales con Ctrl/Cmd
    if(e.ctrlKey || e.metaKey) {
      let handled = false;
      switch(e.key.toLowerCase()) {
        case 'n':
          e.preventDefault();
          e.stopPropagation();
          console.log('Ctrl+N presionado - abriendo modal agregar empresa');
          showModalAgregarEmpresa();
          showShortcutFeedback('Nueva empresa (Ctrl+N)');
          handled = true;
          break;
        case 's':
          e.preventDefault();
          exportToFile();
          showShortcutFeedback('Guardando archivo (Ctrl+S)');
          handled = true;
          break;
        case 'l':
          e.preventDefault();
          loadFromServer();
          showShortcutFeedback('Cargando desde servidor (Ctrl+L)');
          handled = true;
          break;
        case 'f':
          e.preventDefault();
          const searchBox = $('#search');
          if(searchBox) {
            searchBox.focus();
            searchBox.select();
            showShortcutFeedback('Buscar empresa (Ctrl+F)');
          }
          handled = true;
          break;
      }
      if(handled) return;
    }

    // Shortcuts sin modificador (solo cuando no hay input enfocado)
    if(!isInInput) {
      switch(e.key) {
        case 'ArrowUp':
          e.preventDefault();
          navigateEmpresa(-1);
          break;
        case 'ArrowDown':
          e.preventDefault();
          navigateEmpresa(1);
          break;
        case 'Delete':
          if(state.selectedIndex >= 0) {
            e.preventDefault();
            showModalEliminar(state.selectedIndex);
            showShortcutFeedback('Eliminando empresa (Delete)');
          }
          break;
        case '1':
        case '2':
        case '3':
          // Cambiar entre tabs de roles con números
          if(state.selectedIndex >= 0) {
            const emp = getEmpresas()[state.selectedIndex];
            if(emp && emp.roles) {
              const roleIndex = parseInt(e.key) - 1;
              if(roleIndex < emp.roles.length) {
                state.activeRole = emp.roles[roleIndex].id;
                renderEditor();
                showShortcutFeedback(`Cambiando a rol ${e.key}`);
              }
            }
          }
          break;
      }
    }
  }

  function handleInputShortcuts(e) {
    // Verificar si hay un dropdown de autocompletado abierto - si es así, dejarlo manejar el evento
    const dropdown = $('#autocomplete-dropdown');
    if(dropdown && (e.key === 'ArrowUp' || e.key === 'ArrowDown' || e.key === 'Enter' || e.key === 'Tab')) {
      return; // Dejar que el autocomplete maneje estos eventos
    }
    
    // Shortcuts disponibles dentro de inputs de líneas
    if(e.target.closest('.line-item')) {
      const lineItem = e.target.closest('.line-item');
      const idx = parseInt(lineItem.dataset.idx);
      const role = getCurrentRole();
      
      if(e.ctrlKey) {
        switch(e.key) {
          case 'ArrowUp':
            e.preventDefault();
            e.stopPropagation();
            if(role && isFinite(idx) && idx > 0) {
              // Mover línea hacia arriba
              const item = role.lineas.splice(idx, 1)[0];
              role.lineas.splice(idx - 1, 0, item);
              state.focusLineIndex = idx - 1;
              markDirty();
              updateLinesOnly(role, true); // Usar updateLinesOnly preservando scroll
              showShortcutFeedback('Línea movida arriba (Ctrl+↑)');
            }
            return true;
          case 'ArrowDown':
            e.preventDefault();
            e.stopPropagation();
            if(role && isFinite(idx) && idx < role.lineas.length - 1) {
              // Mover línea hacia abajo
              const item = role.lineas.splice(idx, 1)[0];
              role.lineas.splice(idx + 1, 0, item);
              state.focusLineIndex = idx + 1;
              markDirty();
              updateLinesOnly(role, true); // Usar updateLinesOnly preservando scroll
              showShortcutFeedback('Línea movida abajo (Ctrl+↓)');
            }
            return true;
          case 'Enter':
            e.preventDefault();
            // Agregar nueva línea después de la actual
            if(role && isFinite(idx)) {
              role.lineas.splice(idx + 1, 0, '');
              state.focusLineIndex = idx + 1;
              markDirty();
              renderEditor();
              showShortcutFeedback('Nueva línea agregada (Ctrl+Enter)');
            }
            return true;
          case 'd':
            e.preventDefault();
            // Duplicar línea actual
            if(role && isFinite(idx)) {
              const lineText = role.lineas[idx];
              role.lineas.splice(idx + 1, 0, lineText);
              state.focusLineIndex = idx + 1;
              markDirty();
              renderEditor();
              showShortcutFeedback('Línea duplicada (Ctrl+D)');
            }
            return true;
        }
      } else if(e.key === 'Tab' && !e.shiftKey) {
        // Solo prevenir si no hay dropdown de autocomplete
        if(!dropdown) {
          e.preventDefault();
          // Tab: navegar a la siguiente línea
          if(role && isFinite(idx)) {
            const nextIdx = idx + 1;
            if(nextIdx < role.lineas.length) {
              state.focusLineIndex = nextIdx;
              updateLinesOnly(role, true);
            } else {
              // Si estamos en la última línea, crear una nueva vacía
              role.lineas.push('');
              state.focusLineIndex = role.lineas.length - 1;
              markDirty();
              updateLinesOnly(role, true);
            }
          }
          return true;
        }
      } else if(e.key === 'Tab' && e.shiftKey) {
        e.preventDefault();
        // Shift+Tab: navegar a la línea anterior
        if(role && isFinite(idx) && idx > 0) {
          state.focusLineIndex = idx - 1;
          updateLinesOnly(role, true);
        }
        return true;
      } else if(e.key === 'Enter' && !e.ctrlKey && !e.shiftKey) {
        // Enter simple: solo si no hay dropdown
        if(!dropdown) {
          e.preventDefault();
          if(role) {
            role.lineas.push('');
            state.focusLineIndex = role.lineas.length - 1;
            markDirty();
            renderEditor();
          }
          return true;
        }
      } else if(e.key === 'Delete' && e.ctrlKey) {
        e.preventDefault();
        // Ctrl+Delete: eliminar línea actual
        if(role && isFinite(idx)) {
          if(role.lineas.length > 1) { // No eliminar si es la única línea
            role.lineas.splice(idx, 1);
            // Ajustar focus
            const newFocusIdx = Math.min(idx, role.lineas.length - 1);
            state.focusLineIndex = newFocusIdx;
            markDirty();
            updateLinesOnly(role, true);
            showShortcutFeedback('Línea eliminada (Ctrl+Delete)');
          }
        }
        return true;
      }
    }
    return false;
  }

  function navigateEmpresa(direction) {
    const empresas = filteredEmpresas();
    if(empresas.length === 0) return;
    
    let newIndex = -1;
    
    if(state.selectedIndex < 0) {
      // Si no hay empresa seleccionada, seleccionar la primera
      newIndex = empresas[0].idx;
    } else {
      // Encontrar el índice actual en la lista filtrada
      const currentFilteredIndex = empresas.findIndex(item => item.idx === state.selectedIndex);
      if(currentFilteredIndex >= 0) {
        const nextFilteredIndex = currentFilteredIndex + direction;
        if(nextFilteredIndex >= 0 && nextFilteredIndex < empresas.length) {
          newIndex = empresas[nextFilteredIndex].idx;
        }
      }
    }
    
    if(newIndex >= 0 && newIndex !== state.selectedIndex) {
      state.selectedIndex = newIndex;
      renderEmpresaList();
      renderEditor();
      const emp = getEmpresas()[newIndex];
      showShortcutFeedback(`${emp?.empresa?.rut || 'Sin RUT'} - ${emp?.empresa?.nombre || 'Sin nombre'}`);
    }
  }

  function getCurrentRole() {
    if(state.selectedIndex < 0) return null;
    const emp = getEmpresas()[state.selectedIndex];
    if(!emp) return null;
    return emp.roles?.find(r => r.id === state.activeRole);
  }

  function showShortcutFeedback(message, type = 'info') {
    // Crear o actualizar el elemento de feedback
    let feedback = $('#shortcut-feedback');
    if(!feedback) {
      feedback = document.createElement('div');
      feedback.id = 'shortcut-feedback';
      feedback.className = 'shortcut-feedback';
      document.body.appendChild(feedback);
    }
    
    // Limpiar clases anteriores y agregar tipo
    feedback.className = `shortcut-feedback feedback-${type}`;
    feedback.textContent = message;
    feedback.classList.add('show');
    
    // Ocultar después de tiempo variable según tipo
    const timeout = type === 'error' ? 4000 : type === 'success' ? 3000 : 2000;
    clearTimeout(feedback.hideTimer);
    feedback.hideTimer = setTimeout(() => {
      feedback.classList.remove('show');
    }, timeout);
  }

  function updateStatusInRealTime() {
    // Actualizar contador de líneas en tabs
    if(state.selectedIndex >= 0) {
      const emp = getEmpresas()[state.selectedIndex];
      if(emp?.roles) {
        emp.roles.forEach(role => {
          const tab = document.querySelector(`[data-count]`);
          if(tab && tab.textContent.includes(role.id)) {
            tab.setAttribute('data-count', role.lineas?.length || 0);
          }
        });
      }
    }
    
    // Actualizar indicador de empresas faltantes si cambió
    const currentCount = state.empresasFaltantes.length;
    const btnAdd = $('#btnAddEmpresa');
    if(btnAdd) {
      const displayedCount = btnAdd.getAttribute('data-missing-count');
      if(displayedCount !== String(currentCount)) {
        updateAddButtonIndicator();
      }
    }
  }

  // Sistema de autocompletado
  function getAllLineasForRole(roleId) {
    const allLineas = new Set();
    
    // Agregar del template por defecto
    if(DEFAULT_TEMPLATE[roleId]) {
      DEFAULT_TEMPLATE[roleId].forEach(linea => allLineas.add(linea));
    }
    
    // Agregar de todas las empresas existentes
    getEmpresas().forEach(emp => {
      const role = emp.roles?.find(r => r.id === roleId);
      if(role?.lineas) {
        role.lineas.forEach(linea => allLineas.add(linea.trim()));
      }
    });
    
    return Array.from(allLineas).filter(linea => linea.length > 0).sort();
  }

  function getSuggestionsForInput(input, roleId) {
    const value = input.toLowerCase().trim();
    if(value.length < 2) return [];
    
    const allLineas = getAllLineasForRole(roleId);
    return allLineas
      .filter(linea => linea.toLowerCase().includes(value))
      .slice(0, 8); // Máximo 8 sugerencias
  }

  function showAutocompleteSuggestions(input, suggestions) {
    hideAutocompleteSuggestions();
    
    if(suggestions.length === 0) return;
    
    const dropdown = document.createElement('div');
    dropdown.id = 'autocomplete-dropdown';
    dropdown.className = 'autocomplete-dropdown';
    
    suggestions.forEach((suggestion, index) => {
      const item = document.createElement('div');
      item.className = 'autocomplete-item';
      if(index === 0) item.classList.add('selected');
      item.textContent = suggestion;
      item.addEventListener('click', () => {
        input.value = suggestion;
        input.dispatchEvent(new Event('input'));
        hideAutocompleteSuggestions();
        input.focus();
      });
      dropdown.appendChild(item);
    });
    
    // Posicionar el dropdown
    const rect = input.getBoundingClientRect();
    dropdown.style.position = 'fixed';
    dropdown.style.top = (rect.bottom + 2) + 'px';
    dropdown.style.left = rect.left + 'px';
    dropdown.style.width = rect.width + 'px';
    
    document.body.appendChild(dropdown);
    
    // Manejar navegación con teclado
    input.autocompleteIndex = 0;
    input.autocompleteSuggestions = suggestions;
  }

  function hideAutocompleteSuggestions() {
    const dropdown = $('#autocomplete-dropdown');
    if(dropdown) dropdown.remove();
  }

  function handleAutocompleteNavigation(e, input) {
    const dropdown = $('#autocomplete-dropdown');
    if(!dropdown) return false;
    
    const items = dropdown.querySelectorAll('.autocomplete-item');
    if(items.length === 0) return false;
    
    switch(e.key) {
      case 'ArrowDown':
        e.preventDefault();
        input.autocompleteIndex = Math.min(input.autocompleteIndex + 1, items.length - 1);
        updateAutocompleteSelection(items, input.autocompleteIndex);
        return true;
      case 'ArrowUp':
        e.preventDefault();
        input.autocompleteIndex = Math.max(input.autocompleteIndex - 1, 0);
        updateAutocompleteSelection(items, input.autocompleteIndex);
        return true;
      case 'Enter':
        e.preventDefault();
        const selectedItem = items[input.autocompleteIndex];
        if(selectedItem) {
          input.value = selectedItem.textContent;
          input.dispatchEvent(new Event('input'));
        }
        hideAutocompleteSuggestions();
        return true;
      case 'Tab':
        // Para Tab, aplicar sugerencia Y permitir navegación
        const selectedTabItem = items[input.autocompleteIndex];
        if(selectedTabItem) {
          input.value = selectedTabItem.textContent;
          input.dispatchEvent(new Event('input'));
        }
        hideAutocompleteSuggestions();
        // No prevenir el evento para que Tab pueda seguir funcionando para navegación
        return false;
      case 'Escape':
        hideAutocompleteSuggestions();
        return true;
    }
    
    return false;
  }

  function updateAutocompleteSelection(items, selectedIndex) {
    items.forEach((item, index) => {
      item.classList.toggle('selected', index === selectedIndex);
    });
  }

  function init(){
    console.log('EditorApp.init() ejecutándose...');
    // Permitir override de ruta por query param ?path=...
    try{
      const u = new URL(window.location.href);
      const p = u.searchParams.get('path');
      if(p) state.path = p;
    }catch{}

    console.log('Ejecutando attachGlobalHandlers...');
    attachGlobalHandlers();
    console.log('Ejecutando renderEmpresaList...');
    renderEmpresaList();
    console.log('Ejecutando renderEditor...');
    renderEditor();
    console.log('Ejecutando loadFromServer...');
    // Carga automática del JSON al iniciar
    loadFromServer();
  }

  function initWhenReady(){
    if(document.readyState === 'loading'){
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }

  // Función global para agregar empresas desde XBRL
  window.addCompanyFromXBRL = async function(rut, nombre) {
    // Cerrar modal de lista si está abierto
    const modal = document.querySelector('.modal');
    if(modal) modal.remove();
    
    // Abrir modal de agregar empresa con datos prellenados
    await showModalAgregarEmpresa();
    
    // Prellenar datos
    setTimeout(() => {
      const rutInput = $('#modalRut');
      const nombreInput = $('#modalNombre');
      if(rutInput) rutInput.value = rut;
      if(nombreInput) nombreInput.value = nombre;
    }, 100);
  };

  window.EditorApp = { 
    init,
    initWhenReady 
  };
})();
