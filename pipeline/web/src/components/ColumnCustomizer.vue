<template>
  <el-dialog :model-value="visible" title="自定义列" width="1100" top="5vh"
    @update:model-value="v => emit('update:visible', v)" @open="onOpen">
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
        <!-- 常用列：加载/保存/删除 -->
        <div class="cc-presets">
          <span class="cc-preset-lbl">常用列</span>
          <el-select v-model="curPreset" size="small" style="width:190px" clearable placeholder="选择常用列套用"
            @change="onPickPreset">
            <el-option v-for="p in presets" :key="p.id" :label="p.name" :value="p.id">
              <span>{{ p.name }}</span>
              <el-tag v-if="p.is_shared" size="small" type="success" effect="plain" style="margin-left:6px">共享</el-tag>
              <el-tag v-else size="small" type="info" effect="plain" style="margin-left:6px">私有</el-tag>
              <el-icon v-if="p.mine || admin" class="cc-preset-del" title="删除该常用列"
                @click.stop="deletePreset(p)"><Delete /></el-icon>
            </el-option>
          </el-select>
          <el-input v-model="saveName" size="small" style="width:150px" clearable placeholder="另存为常用列名" />
          <el-button size="small" :loading="saving" @click="savePreset">保存为常用列</el-button>
          <span class="cc-hint">{{ admin ? '管理员保存=共享给所有人' : '你保存的仅自己可见' }}</span>
        </div>
        <div class="cc-actions">
          <el-button size="small" @click="resetDefault">恢复默认</el-button>
          <el-button size="small" @click="emit('update:visible', false)">取消</el-button>
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
import { Search, Delete } from '@element-plus/icons-vue'

const props = defineProps({
  visible: Boolean,
  modelValue: { type: Array, default: () => [] },   // colState [{key,visible,pinned}]
  columns: { type: Array, default: () => [] },       // 全部列定义 [{key,label,group,bg?}]
  groups: { type: Array, default: () => [] },         // 有序分类 [{key,label}]
  page: { type: String, required: true },
  admin: { type: Boolean, default: false },
  defaultState: { type: Function, required: true },   // () => colState
})
const emit = defineEmits(['update:visible', 'update:modelValue'])

const colMap = computed(() => Object.fromEntries(props.columns.map(c => [c.key, c])))
const sel = ref([])          // 已选(可见)列，有序 [{key,pinned}]
const selKeys = computed(() => new Set(sel.value.map(s => s.key)))
const search = ref('')
const presets = ref([]); const curPreset = ref(null); const saveName = ref(''); const saving = ref(false)
const dragIdx = ref(-1)

// 从 colState 初始化已选列（可见的，按其顺序）
function stateToSel(state) {
  return (state || []).filter(x => x.visible && colMap.value[x.key]).map(x => ({ key: x.key, pinned: !!x.pinned }))
}
async function onOpen() {
  sel.value = stateToSel(props.modelValue)
  search.value = ''; curPreset.value = null; saveName.value = ''
  await fetchPresets()
}
async function fetchPresets() {
  try { const { data } = await api.get('/column_presets', { params: { page: props.page } }); presets.value = data.presets || [] }
  catch { presets.value = [] }
}

// 上半：分类分组（受搜索过滤）
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

// 下半：已选列
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

// 常用列
function onPickPreset(id) {
  const p = presets.value.find(x => x.id === id); if (!p) return
  sel.value = (p.columns || []).filter(x => colMap.value[x.key]).map(x => ({ key: x.key, pinned: !!x.pinned }))
  ElMessage.success(`已套用常用列「${p.name}」`)
}
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
async function deletePreset(p) {
  try {
    await ElMessageBox.confirm(`删除常用列「${p.name}」？`, '确认', { type: 'warning' })
    await api.delete(`/column_presets/${p.id}`)
    if (curPreset.value === p.id) curPreset.value = null
    ElMessage.success('已删除'); await fetchPresets()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message)) }
}

function resetDefault() { sel.value = stateToSel(props.defaultState()) }
// 确定：已选列(有序,visible) + 其余列(隐藏) 组成新的 colState
function apply() {
  const selMap = Object.fromEntries(sel.value.map(s => [s.key, s]))
  const newState = sel.value.map(s => ({ key: s.key, visible: true, pinned: s.pinned }))
  for (const c of props.columns) if (!selMap[c.key]) newState.push({ key: c.key, visible: false, pinned: false })
  emit('update:modelValue', newState)
  emit('update:visible', false)
}
</script>

<style scoped>
.cc-panel { border: 1px solid #ebeef5; border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
.cc-panel-hd { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px;
  background: #f5f7fa; border-bottom: 1px solid #ebeef5; }
.cc-panel-title { font-size: 13px; color: #303133; font-weight: 600; }
.cc-hint { color: #909399; font-weight: 400; font-size: 12px; margin-left: 4px; }
/* 上半分组 */
.cc-groups { max-height: 260px; overflow-y: auto; padding: 6px 12px 10px; }
.cc-group { margin-top: 8px; }
.cc-group-hd { padding: 4px 0; border-bottom: 1px dashed #ebeef5; margin-bottom: 6px; }
.cc-group-body { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px 8px; }
.cc-opt { margin-right: 0; }
.cc-empty { color: #c0c4cc; font-size: 13px; padding: 12px; text-align: center; }
/* 下半已选 */
.cc-selected { min-height: 70px; max-height: 200px; overflow-y: auto; padding: 10px 12px;
  display: flex; flex-wrap: wrap; gap: 8px; }
.cc-tag { display: flex; align-items: center; gap: 6px; padding: 4px 8px; border: 1px solid #dcdfe6;
  border-radius: 6px; background: #fff; cursor: grab; font-size: 13px; }
.cc-tag.dragging { opacity: .5; border-color: #409EFF; background: #ecf5ff; }
.cc-num { color: #909399; font-size: 12px; min-width: 16px; text-align: center; }
.cc-tag-label { max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cc-pin :deep(.el-checkbox__label) { padding-left: 4px; font-size: 12px; }
.cc-del { color: #c0c4cc; cursor: pointer; font-size: 15px; }
.cc-del:hover { color: #f56c6c; }
/* footer */
.cc-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.cc-presets { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cc-preset-lbl { font-size: 13px; color: #606266; }
.cc-preset-del { float: right; margin-top: 10px; color: #c0c4cc; }
.cc-preset-del:hover { color: #f56c6c; }
.cc-actions { display: flex; gap: 8px; }
</style>
