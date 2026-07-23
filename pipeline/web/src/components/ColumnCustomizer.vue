<template>
  <!-- 触发按钮：点开弹出「常用自定义列」下拉（模板列表 + 配置入口） -->
  <el-popover trigger="click" v-model:visible="pop" :width="300" placement="bottom-start" @show="fetchPresets">
    <template #reference>
      <el-button size="small"><el-icon style="margin-right:4px"><Operation /></el-icon>自定义列</el-button>
    </template>
    <div class="ccp">
      <div class="ccp-hd">
        <span class="ccp-title">常用自定义列</span>
        <el-button size="small" type="primary" @click="openConfig">自定义列配置</el-button>
      </div>
      <div class="ccp-list">
        <div v-for="p in presets" :key="p.id" class="ccp-item" @click="applyPreset(p)">
          <span class="ccp-name" :title="p.name">{{ p.name }}</span>
          <el-tag v-if="p.is_default" type="warning" size="small" effect="dark" class="ccp-tag">默认</el-tag>
          <el-tag :type="p.is_shared ? 'success' : 'info'" size="small" effect="plain" class="ccp-tag">{{ p.is_shared ? '共享' : '私有' }}</el-tag>
          <span class="ccp-ops">
            <el-icon v-if="admin && p.is_shared" class="ccp-ic" :class="{ 'ccp-star': p.is_default }"
              :title="p.is_default ? '取消默认列' : '设为默认列(无自定义的用户默认看到)'" @click.stop="setDefault(p)">
              <StarFilled v-if="p.is_default" /><Star v-else />
            </el-icon>
            <el-icon v-if="p.mine || admin" class="ccp-ic" title="编辑该模板" @click.stop="editPreset(p)"><Edit /></el-icon>
            <el-icon class="ccp-ic" title="复制为新模板" @click.stop="copyPreset(p)"><CopyDocument /></el-icon>
            <el-icon v-if="p.mine || admin" class="ccp-ic ccp-del" title="删除该模板" @click.stop="deletePreset(p)"><Delete /></el-icon>
          </span>
        </div>
        <div v-if="!presets.length" class="ccp-empty">暂无模板<br>点右上「自定义列配置」创建并保存</div>
      </div>
    </div>
  </el-popover>

  <!-- 详细配置弹窗（分类选列 + 已选拖拽/固定/删除 + 另存为常用列） -->
  <el-dialog v-model="dlg" title="自定义列配置" width="1100" top="5vh" append-to-body @open="onDlgOpen">
    <!-- 上半：可添加的列（按分类勾选 + 关键字搜索） -->
    <div class="cc-panel">
      <div class="cc-panel-hd">
        <span class="cc-panel-title">可添加的列</span>
        <el-input v-model="search" size="small" style="width:240px" clearable placeholder="输入关键字搜索">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
      <div class="cc-groups">
        <div v-for="g in groupedCols" :key="g.key" v-show="g.cols.length" class="cc-group">
          <div class="cc-group-hd">
            <el-checkbox :model-value="groupChecked(g)" :indeterminate="groupIndeterminate(g)"
              @change="v => toggleGroup(g, v)"><b>{{ g.label }}</b></el-checkbox>
          </div>
          <div class="cc-group-body">
            <el-checkbox v-for="c in g.cols" :key="c.key" class="cc-opt"
              :model-value="selKeys.has(c.key)" @change="v => toggleCol(c.key, v)">
              {{ c.label }}<el-tag v-if="c.bg" size="small" type="warning" effect="plain" style="margin-left:4px">人工</el-tag>
            </el-checkbox>
          </div>
        </div>
        <div v-if="!groupedCols.some(g => g.cols.length)" class="cc-empty">没有匹配「{{ search }}」的列</div>
      </div>
    </div>

    <!-- 下半：已选列（拖拽排序 + 固定 + 删除） -->
    <div class="cc-panel">
      <div class="cc-panel-hd">
        <span class="cc-panel-title">已选 {{ sel.length }} <span class="cc-hint">· 拖拽调整表头顺序，勾「固定」把列固定到左侧</span></span>
        <el-button size="small" text type="primary" @click="clearAll">清空</el-button>
      </div>
      <div class="cc-selected">
        <div v-for="(s,i) in selDetailed" :key="s.key" class="cc-tag" :class="{dragging:dragIdx===i}"
          draggable="true" @dragstart="dragStart(i)" @dragover.prevent="dragOver(i)" @drop.prevent @dragend="dragEnd">
          <span class="cc-num">{{ i+1 }}</span>
          <span class="cc-tag-label" :title="s.label">{{ s.label }}</span>
          <el-checkbox :model-value="s.pinned" size="small" class="cc-pin" title="固定到左侧"
            @change="v => setPin(s.key, v)">固定</el-checkbox>
          <el-icon class="cc-del" title="移除" @click="removeSel(s.key)"><Delete /></el-icon>
        </div>
        <div v-if="!sel.length" class="cc-empty">未选择任何列，请在上方勾选</div>
      </div>
    </div>

    <template #footer>
      <div class="cc-footer">
        <div class="cc-presets">
          <el-input v-model="saveName" size="small" style="width:180px" clearable placeholder="另存为常用列名" />
          <el-button size="small" :loading="saving" @click="savePreset">保存为常用列</el-button>
          <span class="cc-hint">{{ admin ? '管理员保存=共享模板(全员可套用)' : '你保存的仅自己可见' }}</span>
        </div>
        <div class="cc-actions">
          <el-button size="small" @click="resetDefault">恢复默认</el-button>
          <el-button size="small" @click="dlg = false">取消</el-button>
          <el-button size="small" type="primary" @click="apply">确定</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Delete, Operation, Edit, CopyDocument, Star, StarFilled } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },   // colState [{key,visible,pinned}]
  columns: { type: Array, default: () => [] },       // 全部列定义 [{key,label,group,bg?}]
  groups: { type: Array, default: () => [] },         // 有序分类 [{key,label}]
  page: { type: String, required: true },
  admin: { type: Boolean, default: false },
  defaultState: { type: Function, required: true },   // () => colState
})
const emit = defineEmits(['update:modelValue'])

const colMap = computed(() => Object.fromEntries(props.columns.map(c => [c.key, c])))
const pop = ref(false)       // 下拉是否展开
const dlg = ref(false)       // 配置弹窗是否打开
const presets = ref([])
const sel = ref([])          // 配置弹窗内：已选(可见)列，有序 [{key,pinned}]
const selKeys = computed(() => new Set(sel.value.map(s => s.key)))
const search = ref(''); const saveName = ref(''); const saving = ref(false)
const dragIdx = ref(-1)

async function fetchPresets() {
  try { const { data } = await api.get('/column_presets', { params: { page: props.page } }); presets.value = data.presets || [] }
  catch { presets.value = [] }
}

// colState <-> 已选列
function stateToSel(state) {
  return (state || []).filter(x => x.visible && colMap.value[x.key]).map(x => ({ key: x.key, pinned: !!x.pinned }))
}
// 由「有序已选列」组装完整 colState（已选=可见有序，其余=隐藏）
function buildState(selArr) {
  const m = Object.fromEntries(selArr.map(s => [s.key, s]))
  const st = selArr.map(s => ({ key: s.key, visible: true, pinned: !!s.pinned }))
  for (const c of props.columns) if (!m[c.key]) st.push({ key: c.key, visible: false, pinned: false })
  return st
}

// —— 下拉：套用模板（直接应用到表格） ——
function applyPreset(p) {
  const arr = (p.columns || []).filter(x => colMap.value[x.key]).map(x => ({ key: x.key, pinned: !!x.pinned }))
  if (!arr.length) return ElMessage.warning('该模板无可用列')
  emit('update:modelValue', buildState(arr))
  pop.value = false
  ElMessage.success(`已按「${p.name}」显示`)
}
function openConfig() { pendingEdit.value = null; pop.value = false; dlg.value = true }

// —— 编辑/复制模板 ——
const pendingEdit = ref(null)   // 打开配置弹窗时若有值，则载入该模板(编辑)而非当前表格状态
function editPreset(p) {
  pendingEdit.value = { columns: p.columns || [], name: p.name }
  pop.value = false; dlg.value = true
}
function uniqName(base) {   // 在已有模板名里取不重复的名字：X 副本 / X 副本2 …
  const names = new Set(presets.value.map(p => p.name))
  if (!names.has(base)) return base
  let i = 2; while (names.has(base + i)) i++; return base + i
}
async function copyPreset(p) {
  const name = uniqName((p.name || '模板') + ' 副本')
  try {
    await api.post('/column_presets', { page: props.page, name, columns: (p.columns || []).map(x => ({ key: x.key, pinned: !!x.pinned })) })
    ElMessage.success(`已复制为「${name}」`)
    await fetchPresets()
  } catch (e) { ElMessage.error('复制失败：' + (e.response?.data?.detail || e.message)) }
}

// —— 配置弹窗 ——
function onDlgOpen() {
  search.value = ''
  if (pendingEdit.value) {   // 编辑模板：载入其列 + 预填名称(保存即覆盖同名)
    sel.value = pendingEdit.value.columns.filter(x => colMap.value[x.key]).map(x => ({ key: x.key, pinned: !!x.pinned }))
    saveName.value = pendingEdit.value.name; pendingEdit.value = null
  } else {                    // 普通打开：以当前表格显示的列为准
    sel.value = stateToSel(props.modelValue); saveName.value = ''
  }
}
const groupedCols = computed(() => {
  const kw = search.value.trim().toLowerCase()
  return props.groups.map(g => ({
    key: g.key, label: g.label,
    cols: props.columns.filter(c => c.group === g.key && (!kw || c.label.toLowerCase().includes(kw)))
  }))
})
function groupChecked(g) { return g.cols.length && g.cols.every(c => selKeys.value.has(c.key)) }
function groupIndeterminate(g) {
  const n = g.cols.filter(c => selKeys.value.has(c.key)).length
  return n > 0 && n < g.cols.length
}
function toggleGroup(g, checked) {
  if (checked) { for (const c of g.cols) if (!selKeys.value.has(c.key)) sel.value.push({ key: c.key, pinned: false }) }
  else { const rm = new Set(g.cols.map(c => c.key)); sel.value = sel.value.filter(s => !rm.has(s.key)) }
}
function toggleCol(key, checked) {
  if (checked) { if (!selKeys.value.has(key)) sel.value.push({ key, pinned: false }) }
  else sel.value = sel.value.filter(s => s.key !== key)
}
const selDetailed = computed(() => sel.value.map(s => ({ key: s.key, pinned: s.pinned, label: colMap.value[s.key]?.label || s.key })))
function removeSel(key) { sel.value = sel.value.filter(s => s.key !== key) }
function setPin(key, v) { const s = sel.value.find(x => x.key === key); if (s) s.pinned = v }
function clearAll() { sel.value = [] }
function dragStart(i) { dragIdx.value = i }
function dragOver(i) {
  if (dragIdx.value === -1 || dragIdx.value === i) return
  const arr = sel.value; const [m] = arr.splice(dragIdx.value, 1); arr.splice(i, 0, m); dragIdx.value = i
}
function dragEnd() { dragIdx.value = -1 }

async function savePreset() {
  const name = saveName.value.trim()
  if (!name) return ElMessage.warning('请先填写常用列名')
  if (!sel.value.length) return ElMessage.warning('未选择任何列')
  saving.value = true
  try {
    await api.post('/column_presets', { page: props.page, name, columns: sel.value.map(s => ({ key: s.key, pinned: s.pinned })) })
    ElMessage.success(props.admin ? `已保存并共享「${name}」` : `已保存「${name}」`)
    saveName.value = ''; await fetchPresets()
  } catch (e) { ElMessage.error('保存失败：' + (e.response?.data?.detail || e.message)) }
  finally { saving.value = false }
}
// —— 管理员：设/取消默认列（全员共享，无本地配置的用户初始按它显示）——
async function setDefault(p) {
  try {
    const { data } = await api.post(`/column_presets/${p.id}/default`)
    await fetchPresets()
    ElMessage.success(data.is_default ? `已将「${p.name}」设为默认列` : '已取消默认列')
  } catch (e) { ElMessage.error('设置失败：' + (e.response?.data?.detail || e.message)) }
}
async function deletePreset(p) {
  try {
    await ElMessageBox.confirm(`删除模板「${p.name}」？`, '确认', { type: 'warning' })
    await api.delete(`/column_presets/${p.id}`)
    ElMessage.success('已删除'); await fetchPresets()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message)) }
}

function resetDefault() { sel.value = stateToSel(props.defaultState()) }
function apply() { emit('update:modelValue', buildState(sel.value)); dlg.value = false }
</script>

<style scoped>
/* 下拉：常用自定义列 */
.ccp-hd { display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding-bottom: 8px; margin-bottom: 6px; border-bottom: 1px solid #ebeef5; }
.ccp-title { font-size: 13px; font-weight: 600; color: #303133; }
.ccp-list { max-height: 320px; overflow-y: auto; }
.ccp-item { display: flex; align-items: center; gap: 6px; padding: 7px 8px; border-radius: 6px; cursor: pointer; }
.ccp-item:hover { background: #ecf5ff; }
.ccp-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; color: #303133; }
.ccp-tag { flex-shrink: 0; }
.ccp-ops { display: flex; align-items: center; gap: 8px; flex-shrink: 0; margin-left: 4px; }
.ccp-ic { color: #a8abb2; cursor: pointer; font-size: 15px; }
.ccp-ic:hover { color: #409EFF; }
.ccp-del:hover { color: #f56c6c; }
.ccp-star { color: #e6a23c; }
.ccp-star:hover { color: #e6a23c; }
.ccp-empty { color: #c0c4cc; font-size: 12px; text-align: center; padding: 20px 8px; line-height: 1.8; }
/* 配置弹窗面板 */
.cc-panel { border: 1px solid #ebeef5; border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
.cc-panel-hd { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px;
  background: #f5f7fa; border-bottom: 1px solid #ebeef5; }
.cc-panel-title { font-size: 13px; color: #303133; font-weight: 600; }
.cc-hint { color: #909399; font-weight: 400; font-size: 12px; margin-left: 4px; }
.cc-groups { max-height: 240px; overflow-y: auto; padding: 6px 12px 10px; }
.cc-group { margin-top: 8px; }
.cc-group-hd { padding: 4px 0; border-bottom: 1px dashed #ebeef5; margin-bottom: 6px; }
.cc-group-body { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px 8px; }
.cc-opt { margin-right: 0; }
.cc-empty { color: #c0c4cc; font-size: 13px; padding: 12px; text-align: center; }
.cc-selected { min-height: 70px; max-height: 240px; overflow-y: auto; padding: 10px 12px;
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; align-content: start; }
.cc-tag { display: flex; align-items: center; gap: 6px; padding: 5px 8px; border: 1px solid #dcdfe6;
  border-radius: 6px; background: #f5f7fa; cursor: grab; font-size: 13px; min-width: 0; }
.cc-tag.dragging { opacity: .5; border-color: #409EFF; background: #ecf5ff; }
.cc-num { color: #909399; font-size: 12px; min-width: 18px; text-align: right; flex-shrink: 0; }
.cc-tag-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cc-pin { flex-shrink: 0; }
.cc-pin :deep(.el-checkbox__label) { padding-left: 4px; font-size: 12px; }
.cc-del { color: #c0c4cc; cursor: pointer; font-size: 15px; flex-shrink: 0; }
.cc-del:hover { color: #f56c6c; }
.cc-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.cc-presets { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cc-actions { display: flex; gap: 8px; }
</style>
