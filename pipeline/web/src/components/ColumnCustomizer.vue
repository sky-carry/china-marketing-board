<template>
  <el-dialog :model-value="visible" title="自定义列" width="1100" top="5vh"
    @update:model-value="v => emit('update:visible', v)" @open="onOpen">
    <el-tabs v-model="tab" class="cc-tabs">
      <!-- Tab1：常用自定义列（模板/预设，点选套用） -->
      <el-tab-pane name="presets">
        <template #label>常用自定义列<span v-if="presets.length" class="cc-cnt">{{ presets.length }}</span></template>
        <div class="cc-preset-list">
          <div v-for="p in presets" :key="p.id" class="cc-preset-card" @click="usePreset(p)">
            <div class="cc-preset-main">
              <span class="cc-preset-name" :title="p.name">{{ p.name }}</span>
              <el-tag :type="p.is_shared ? 'success' : 'info'" size="small" effect="plain">{{ p.is_shared ? '共享模板' : '我的私有' }}</el-tag>
            </div>
            <div class="cc-preset-sub">
              <span>{{ p.columns?.length || 0 }} 列 · {{ p.owner_name || '—' }}</span>
              <span class="cc-preset-ops">
                <el-button size="small" type="primary" text @click.stop="usePreset(p)">套用</el-button>
                <el-icon v-if="p.mine || admin" class="cc-del" title="删除该常用列" @click.stop="deletePreset(p)"><Delete /></el-icon>
              </span>
            </div>
          </div>
          <div v-if="!presets.length" class="cc-empty cc-empty-lg">
            暂无常用列。切到「自定义列」配置好后，用下方「另存为常用列」保存即可。<br>
            <span v-if="admin">你是管理员，保存的将作为<b>共享模板</b>供所有人套用。</span>
            <span v-else>你保存的仅自己可见。</span>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab2：自定义列（详细配置） -->
      <el-tab-pane label="自定义列" name="config">
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
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <div class="cc-footer">
        <div class="cc-presets">
          <el-input v-model="saveName" size="small" style="width:180px" clearable placeholder="另存为常用列名" />
          <el-button size="small" :loading="saving" @click="savePreset">保存为常用列</el-button>
          <span class="cc-hint">{{ admin ? '管理员保存=共享模板(全员可套用)' : '你保存的仅自己可见' }}</span>
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
const tab = ref('presets')   // presets=常用自定义列 / config=自定义列
const presets = ref([]); const saveName = ref(''); const saving = ref(false)
const dragIdx = ref(-1)

// 从 colState 初始化已选列（可见的，按其顺序）
function stateToSel(state) {
  return (state || []).filter(x => x.visible && colMap.value[x.key]).map(x => ({ key: x.key, pinned: !!x.pinned }))
}
async function onOpen() {
  sel.value = stateToSel(props.modelValue)
  search.value = ''; saveName.value = ''
  await fetchPresets()
  tab.value = presets.value.length ? 'presets' : 'config'   // 有模板先看模板，否则直接进配置
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

// 常用列：套用一个模板 -> 载入到配置并切到「自定义列」页供查看/微调
function usePreset(p) {
  sel.value = (p.columns || []).filter(x => colMap.value[x.key]).map(x => ({ key: x.key, pinned: !!x.pinned }))
  tab.value = 'config'
  ElMessage.success(`已套用「${p.name}」，可继续微调后点确定`)
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
.cc-tabs :deep(.el-tabs__header) { margin-bottom: 10px; }
.cc-cnt { display: inline-block; min-width: 16px; height: 16px; line-height: 16px; padding: 0 4px; margin-left: 6px;
  font-size: 11px; color: #fff; background: #409EFF; border-radius: 8px; text-align: center; }
/* 常用自定义列：模板卡片列表 */
.cc-preset-list { min-height: 200px; max-height: 420px; overflow-y: auto;
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; padding: 2px; }
.cc-preset-card { border: 1px solid #e4e7ed; border-radius: 8px; padding: 10px 12px; cursor: pointer;
  transition: all .15s; background: #fff; align-self: start; }
.cc-preset-card:hover { border-color: #409EFF; box-shadow: 0 2px 8px rgba(64,158,255,.15); }
.cc-preset-main { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.cc-preset-name { font-size: 14px; font-weight: 600; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cc-preset-sub { display: flex; align-items: center; justify-content: space-between; color: #909399; font-size: 12px; }
.cc-preset-ops { display: flex; align-items: center; gap: 6px; }
.cc-empty-lg { min-height: 180px; display: flex; flex-direction: column; align-items: center; justify-content: center; line-height: 1.9; }
/* 配置面板 */
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
/* 已选 */
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
/* footer */
.cc-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.cc-presets { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cc-actions { display: flex; gap: 8px; }
</style>
