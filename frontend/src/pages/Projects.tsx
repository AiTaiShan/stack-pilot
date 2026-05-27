import React, { useEffect, useState } from 'react'
import { Table, Button, Space, message, Modal, Form, Input } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

const Projects: React.FC = () => {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()
  const navigate = useNavigate()

  const fetchProjects = async () => {
    setLoading(true)
    try {
      const response = await axios.get('/api/v1/projects/', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
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
      await axios.post('/api/v1/projects/', values, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      message.success('项目创建成功')
      setModalVisible(false)
      form.resetFields()
      fetchProjects()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '创建失败')
    }
  }

  const columns = [
    { title: '项目名称', dataIndex: 'name', key: 'name' },
    { title: 'Git地址', dataIndex: 'git_url', key: 'git_url', ellipsis: true },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Space>
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
    </div>
  )
}

export default Projects
