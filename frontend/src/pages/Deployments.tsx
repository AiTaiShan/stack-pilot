import React, { useEffect, useState } from 'react'
import { Table, Tag, Space, message } from 'antd'
import axios from 'axios'

const statusColors: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  paused: 'warning',
  cancelled: 'default',
  success: 'success',
  failed: 'error',
  rolling_back: 'warning',
  rolled_back: 'default',
}

const Deployments: React.FC = () => {
  const [deployments, setDeployments] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const fetchDeployments = async () => {
      setLoading(true)
      try {
        const projectsRes = await axios.get('/api/v1/projects/', {
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
        })
        const projects = projectsRes.data.data.items || []
        const allDeployments: any[] = []

        for (const project of projects) {
          try {
            const deployRes = await axios.get(`/api/v1/deployments/?project_id=${project.id}`, {
              headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
            })
            const items = deployRes.data.data?.items || []
            allDeployments.push(...items.map((d: any) => ({ ...d, project_name: project.name })))
          } catch (e) {
            // 忽略单个项目的部署查询失败
          }
        }

        setDeployments(allDeployments)
      } catch (error) {
        message.error('获取部署记录失败')
      } finally {
        setLoading(false)
      }
    }
    fetchDeployments()
  }, [])

  const columns = [
    { title: '项目', dataIndex: 'project_name', key: 'project_name' },
    { title: '部署ID', dataIndex: 'id', key: 'id', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (status: string) => <Tag color={statusColors[status] || 'default'}>{status}</Tag>
    },
    { title: '平台', dataIndex: 'platform', key: 'platform' },
    { title: '部署URL', dataIndex: 'deploy_url', key: 'deploy_url', ellipsis: true },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Space>
          {record.status === 'running' && <a>暂停</a>}
          {record.status === 'paused' && <a>恢复</a>}
          {record.status === 'running' && <a>取消</a>}
          {['success', 'failed'].includes(record.status) && <a>回滚</a>}
        </Space>
      )
    }
  ]

  return (
    <div>
      <h2>部署记录</h2>
      <Table columns={columns} dataSource={deployments} loading={loading} rowKey="id" />
    </div>
  )
}

export default Deployments
