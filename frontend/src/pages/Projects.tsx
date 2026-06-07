import React, { useEffect, useState } from 'react'
import { Table, Button, Space, message, Modal, Form, Input } from 'antd'
import { PlusOutlined, EditOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import client from '../api/client'

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

const Projects: React.FC = () => {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [editingProject, setEditingProject] = useState<any>(null)
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  const navigate = useNavigate()

  const fetchProjects = async () => {
    setLoading(true)
    try {
      const response = await client.get('/projects')
      setProjects(response.data.data.items)
    } catch (error) {
      message.error('获取项目列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchProjects() }, [])

  const handleCreate = async (values: { name: string; git_url: string; description?: string }) => {
    try {
      await client.post('/projects', values)
      message.success('项目创建成功')
      setModalVisible(false)
      form.resetFields()
      fetchProjects()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '创建失败')
    }
  }

  const openEditModal = (record: any) => {
    setEditingProject(record)
    setEditModalVisible(true)
    editForm.setFieldsValue({
      name: record.name,
      description: record.description,
    })
  }

  const handleEdit = async (values: { name: string; description?: string }) => {
    try {
      await client.put(`/projects/${editingProject.id}`, values)
      message.success('项目更新成功')
      setEditModalVisible(false)
      setEditingProject(null)
      fetchProjects()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新失败')
    }
  }

  const columns = [
    { title: '项目名称', dataIndex: 'name', key: 'name' },
    { title: 'Git地址', dataIndex: 'git_url', key: 'git_url', ellipsis: true },
    { title: '默认分支', dataIndex: 'default_branch', key: 'default_branch' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: (text: string) => formatDate(text) },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEditModal(record)}>编辑</Button>
          <Button type="link" onClick={() => navigate(`/projects/${record.id}`)}>详情</Button>
        </Space>
      )
    }
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2>项目管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
          创建项目
        </Button>
      </div>
      <Table columns={columns} dataSource={projects} loading={loading} rowKey="id" />
      <Modal title="创建项目" open={modalVisible} onCancel={() => setModalVisible(false)} onOk={() => form.submit()}>
        <Form form={form} onFinish={handleCreate} layout="vertical">
          <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="请输入项目名称" />
          </Form.Item>
          <Form.Item name="git_url" label="Git地址" rules={[{ required: true, message: '请输入Git地址' }]}>
            <Input placeholder="https://github.com/user/repo.git" />
          </Form.Item>
          <Form.Item name="description" label="项目描述">
            <Input.TextArea placeholder="项目描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>
      <Modal title="编辑项目" open={editModalVisible} onCancel={() => { setEditModalVisible(false); setEditingProject(null) }} onOk={() => editForm.submit()}>
        <Form form={editForm} onFinish={handleEdit} layout="vertical">
          <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="项目描述">
            <Input.TextArea />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Projects
