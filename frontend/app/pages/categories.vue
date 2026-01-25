<template>
  <div class="categories-page">
    <header class="page-header">
      <h1 class="page-title">Categories Admin</h1>
      <button class="primary-btn" @click="openGroupModal()">
        + Add Group
      </button>
    </header>

    <!-- Error Banner -->
    <div v-if="error" class="error-banner">
      {{ error }}
      <button class="close-btn" @click="error = null">×</button>
    </div>

    <!-- Loading State -->
    <div v-if="pending" class="loading-state">
      <div class="spinner"></div>
      <p>Loading categories...</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="!categoryGroups.length" class="empty-state">
      <div class="empty-icon">🏷️</div>
      <h2>No categories yet</h2>
      <p>Create category groups to organize your budget.</p>
    </div>

    <!-- Category Groups List -->
    <div v-else class="groups-list">
      <div v-for="group in categoryGroups" :key="group.category_group_id" class="group-card">
        <div class="group-header">
          <div class="group-info">
            <span class="group-order">{{ group.sort_order }}</span>
            <h3 class="group-name">{{ group.name }}</h3>
          </div>
          <div class="group-actions">
            <button class="icon-btn" @click="openGroupModal(group)" title="Edit Group">✏️</button>
            <button class="icon-btn delete" @click="confirmDeleteGroup(group)" title="Delete Group">🗑️</button>
          </div>
        </div>

        <div class="category-list">
          <div v-for="category in group.categories" :key="category.category_id" class="category-row">
            <div class="category-info">
              <span class="category-order">{{ category.sort_order }}</span>
              <span class="category-name">{{ category.name }}</span>
              <span :class="['category-type-badge', category.type]">{{ category.type }}</span>
              <span v-if="!category.is_active" class="category-inactive-badge">Inactive</span>
            </div>
            <div class="category-actions">
              <button class="icon-btn" @click="openCategoryModal(group.category_group_id, category)" title="Edit Category">✏️</button>
              <button class="icon-btn delete" @click="confirmDeleteCategory(category)" title="Delete Category">🗑️</button>
            </div>
          </div>
          <button class="add-category-btn" @click="openCategoryModal(group.category_group_id)">
            + Add Category
          </button>
        </div>
      </div>
    </div>

    <!-- Group Modal -->
    <div v-if="showGroupModal" class="modal-overlay" @click.self="closeGroupModal">
      <div class="modal">
        <div class="modal-header">
          <h3>{{ editingGroup ? 'Edit Group' : 'Add Group' }}</h3>
          <button class="close-btn" @click="closeGroupModal">×</button>
        </div>
        <form @submit.prevent="saveGroup">
          <div class="form-group">
            <label for="group-name">Name</label>
            <input id="group-name" v-model="groupForm.name" required placeholder="e.g., Housing, Food" />
          </div>
          <div class="form-group">
            <label for="group-order">Sort Order</label>
            <input id="group-order" type="number" v-model.number="groupForm.sort_order" required />
          </div>
          <div class="modal-footer">
            <button type="button" class="secondary-btn" @click="closeGroupModal">Cancel</button>
            <button type="submit" class="primary-btn" :disabled="saving">
              {{ saving ? 'Saving...' : 'Save Group' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Category Modal -->
    <div v-if="showCategoryModal" class="modal-overlay" @click.self="closeCategoryModal">
      <div class="modal">
        <div class="modal-header">
          <h3>{{ editingCategory ? 'Edit Category' : 'Add Category' }}</h3>
          <button class="close-btn" @click="closeCategoryModal">×</button>
        </div>
        <form @submit.prevent="saveCategory">
          <div class="form-group">
            <label for="cat-name">Name</label>
            <input id="cat-name" v-model="categoryForm.name" required placeholder="e.g., Rent, Groceries" />
          </div>
          <div class="form-row">
            <div class="form-group">
              <label for="cat-type">Type</label>
              <select id="cat-type" v-model="categoryForm.type">
                <option value="expense">Expense</option>
                <option value="income">Income</option>
                <option value="transfer">Transfer</option>
              </select>
            </div>
            <div class="form-group">
              <label for="cat-order">Sort Order</label>
              <input id="cat-order" type="number" v-model.number="categoryForm.sort_order" required />
            </div>
          </div>
          <div class="form-group checkbox">
            <input id="cat-active" type="checkbox" v-model="categoryForm.is_active" />
            <label for="cat-active">Active</label>
          </div>
          <div class="modal-footer">
            <button type="button" class="secondary-btn" @click="closeCategoryModal">Cancel</button>
            <button type="submit" class="primary-btn" :disabled="saving">
              {{ saving ? 'Saving...' : 'Save Category' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const API_BASE = 'http://localhost:12344'

interface Category {
  category_id: string
  group_id: string
  name: string
  sort_order: number
  type: 'income' | 'expense' | 'transfer'
  is_active: boolean
}

interface CategoryGroup {
  category_group_id: string
  name: string
  sort_order: number
  categories: Category[]
}

// --- State ---
const categoryGroups = ref<CategoryGroup[]>([])
const pending = ref(true)
const error = ref<string | null>(null)
const saving = ref(false)

// Modals
const showGroupModal = ref(false)
const showCategoryModal = ref(false)
const editingGroup = ref<CategoryGroup | null>(null)
const editingCategory = ref<Category | null>(null)

// Forms
const groupForm = ref({
  name: '',
  sort_order: 0
})

const categoryForm = ref({
  name: '',
  group_id: '',
  type: 'expense' as const,
  sort_order: 0,
  is_active: true
})

// --- Data Fetching ---
const fetchCategories = async () => {
  pending.value = true
  error.value = null
  try {
    const res = await fetch(`${API_BASE}/category-groups`)
    if (!res.ok) throw new Error('Failed to fetch categories')
    categoryGroups.value = await res.json()
  } catch (err: any) {
    error.value = err.message
  } finally {
    pending.value = false
  }
}

// --- Group Actions ---
const openGroupModal = (group?: CategoryGroup) => {
  if (group) {
    editingGroup.value = group
    groupForm.value = {
      name: group.name,
      sort_order: group.sort_order
    }
  } else {
    editingGroup.value = null
    groupForm.value = {
      name: '',
      sort_order: categoryGroups.value.length * 10
    }
  }
  showGroupModal.value = true
}

const closeGroupModal = () => {
  showGroupModal.value = false
  editingGroup.value = null
}

const saveGroup = async () => {
  saving.value = true
  try {
    const url = editingGroup.value 
      ? `${API_BASE}/category-groups/${editingGroup.value.category_group_id}`
      : `${API_BASE}/category-groups`
    
    const method = editingGroup.value ? 'PUT' : 'POST'
    
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(groupForm.value)
    })
    
    if (!res.ok) throw new Error('Failed to save group')
    
    await fetchCategories()
    closeGroupModal()
  } catch (err: any) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

const confirmDeleteGroup = async (group: CategoryGroup) => {
  if (group.categories.length > 0) {
    alert('Cannot delete a group that contains categories. Move or delete categories first.')
    return
  }
  
  if (!confirm(`Are you sure you want to delete the group "${group.name}"?`)) return
  
  try {
    const res = await fetch(`${API_BASE}/category-groups/${group.category_group_id}`, {
      method: 'DELETE'
    })
    if (!res.ok) throw new Error('Failed to delete group')
    await fetchCategories()
  } catch (err: any) {
    error.value = err.message
  }
}

// --- Category Actions ---
const openCategoryModal = (groupId: string, category?: Category) => {
  if (category) {
    editingCategory.value = category
    categoryForm.value = {
      name: category.name,
      group_id: category.group_id,
      type: category.type,
      sort_order: category.sort_order,
      is_active: category.is_active
    }
  } else {
    editingCategory.value = null
    const group = categoryGroups.value.find(g => g.category_group_id === groupId)
    categoryForm.value = {
      name: '',
      group_id: groupId,
      type: 'expense',
      sort_order: (group?.categories.length || 0) * 10,
      is_active: true
    }
  }
  showCategoryModal.value = true
}

const closeCategoryModal = () => {
  showCategoryModal.value = false
  editingCategory.value = null
}

const saveCategory = async () => {
  saving.value = true
  try {
    const url = editingCategory.value 
      ? `${API_BASE}/categories/${editingCategory.value.category_id}`
      : `${API_BASE}/categories`
    
    const method = editingCategory.value ? 'PUT' : 'POST'
    
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(categoryForm.value)
    })
    
    if (!res.ok) throw new Error('Failed to save category')
    
    await fetchCategories()
    closeCategoryModal()
  } catch (err: any) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

const confirmDeleteCategory = async (category: Category) => {
  if (!confirm(`Are you sure you want to delete the category "${category.name}"?`)) return
  
  try {
    const res = await fetch(`${API_BASE}/categories/${category.category_id}`, {
      method: 'DELETE'
    })
    if (!res.ok) throw new Error('Failed to delete category')
    await fetchCategories()
  } catch (err: any) {
    error.value = err.message
  }
}

onMounted(() => {
  fetchCategories()
})
</script>

<style scoped>
.categories-page {
  padding: 24px;
  max-width: 1000px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.page-title {
  font-size: 1.8rem;
  font-weight: 700;
  margin: 0;
}

.primary-btn {
  background: var(--accent-color);
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.primary-btn:hover {
  opacity: 0.9;
}

.primary-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.secondary-btn {
  background: white;
  color: var(--text-color);
  border: 1px solid var(--border-color);
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
}

.secondary-btn:hover {
  background: var(--nav-hover-bg);
}

.error-banner {
  background: #fee2e2;
  color: #dc2626;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: inherit;
  cursor: pointer;
  padding: 0 4px;
}

.loading-state, .empty-state {
  text-align: center;
  padding: 60px;
  color: var(--text-muted);
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 16px;
}

.spinner {
  border: 3px solid #f3f3f3;
  border-top: 3px solid var(--accent-color);
  border-radius: 50%;
  width: 30px;
  height: 30px;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.groups-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(450px, 1fr));
  gap: 24px;
}

.group-card {
  background: white;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  display: flex;
  flex-direction: column;
}

.group-header {
  background: #f8fafc;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.group-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.group-order {
  background: var(--border-color);
  color: var(--text-muted);
  font-size: 0.75rem;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
}

.group-name {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
}

.group-actions, .category-actions {
  display: flex;
  gap: 4px;
}

.icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  font-size: 1rem;
  transition: background 0.2s;
}

.icon-btn:hover {
  background: #e2e8f0;
}

.icon-btn.delete:hover {
  background: #fee2e2;
}

.category-list {
  padding: 8px 0;
}

.category-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 20px;
  border-bottom: 1px solid #f1f5f9;
}

.category-row:last-of-type {
  border-bottom: none;
}

.category-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.category-order {
  color: var(--text-muted);
  font-size: 0.75rem;
  width: 20px;
}

.category-name {
  font-weight: 500;
}

.category-type-badge {
  font-size: 0.7rem;
  text-transform: uppercase;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
}

.category-type-badge.income {
  background: #dcfce7;
  color: #166534;
}

.category-type-badge.expense {
  background: #f1f5f9;
  color: #475569;
}

.category-type-badge.transfer {
  background: #fef9c3;
  color: #854d0e;
}

.category-inactive-badge {
  font-size: 0.7rem;
  background: #fee2e2;
  color: #991b1b;
  padding: 2px 6px;
  border-radius: 4px;
}

.add-category-btn {
  width: 100%;
  padding: 12px;
  background: none;
  border: none;
  border-top: 1px solid #f1f5f9;
  color: var(--accent-color);
  font-weight: 600;
  cursor: pointer;
  text-align: left;
  padding-left: 20px;
}

.add-category-btn:hover {
  background: #f8fafc;
}

/* Modal Styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 16px;
  width: 100%;
  max-width: 450px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.modal-header {
  padding: 20px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  margin: 0;
}

form {
  padding: 20px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.form-group input, .form-group select {
  width: 100%;
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 1rem;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-group.checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-group.checkbox input {
  width: auto;
}

.form-group.checkbox label {
  margin-bottom: 0;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}
</style>