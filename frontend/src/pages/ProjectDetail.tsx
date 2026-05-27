import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Card, Descriptions, Button, Table, Space, message, Modal, Select } from 'antd'
import axios from 'axios'

const ProjectDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const [project, setProject] = useState<any>(null)
  const [deployments, setDeployments] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [deployModalVisible, setDeployModalVisible] = useState(false)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const [projectRes, deploymentsRes] = await Promise.all([
          axios.get(`/api/v1/projects/${id}`, {
            headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
          }),
          axios.get(`/api/v1/deployments/?project_id=${id}`, {
            headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
          })
        ])
        setProject(projectRes.data.data)
        setDeployments(deploymentsRes.data.data.items || [])
      } catch (error) {
        message.error('获取项目信息失败')
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [id])

  const handleDeploy = async (values: { branch: string; platform: string }) => {
    try {
      await axios.post('/api/v1/deployments/', {
        git_url: project.git_url,
        branch: values.branch,
        platform: values.platform,
        config: { project_id: id }
      }, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      message.success('部署已触发')
      setDeployModalVisible(false)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '部署失败')
    }
  }

  const deploymentColumns = [
    { title: '状态', dataIndex: 'status', key: 'status' },
    { title: '平台', dataIndex: 'platform', key: 'platform' },
    { title: '部署URL', dataIndex: 'deploy_url', key: 'deploy_url', ellipsis: true },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
  ]

  if (!project) return <div>加载中...</div>

  return (
    <div>
      <Card title="项目详情" extra={
        <Button type="primary" onClick={() => setDeployModalVisible(true)}>触发部署</Button>
      }>
        <Descriptions column={2}>
          <Descriptions.Item label="项目名称">{project.name}</Descriptions.Item>
          <Descriptions.Item label="Git地址">{project.git_url}</Descriptions.Item>
          <Descriptions.Item label="默认分支">{project.default_branch}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{project.created_at}</Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>{project.description || '无'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="部署记录" style={{ marginTop: 16 }}>
        <Table columns={deploymentColumns} dataSource={deployments} loading={loading} rowKey="id" />
      </Card>

      <Modal title="触发部署" open={deployModalVisible} onCancel={() => setDeployModalVisible(false)} onOk={() => handleDeploy({ branch: 'main', platform: 'k8s' })}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Select placeholder="选择分支" style={{ width: '100%' }}>
            <Select.Option value="main">main</Select.Option>
            <Select.Option value="develop">develop</Select.Option>
          </Select>
          <Select placeholder="选择平台" style={{ width: '100%' }}>
            <Select.Option value="k8s">Kubernetes</Select.Option>
            <Select.Option value="coolify">Coolify</Select.Option>
          </Select>
        </Space>
      </Modal>
    </div>
  )
}

export default ProjectDetail
