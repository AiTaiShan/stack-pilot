import React, { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic } from 'antd'
import { ProjectOutlined, CloudServerOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import client from '../api/client'

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState({ projects: 0, deployments: 0, success: 0, failed: 0 })

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [projectsRes, statsRes] = await Promise.all([
          client.get('/projects'),
          client.get('/monitoring/stats')
        ])
        setStats({
          projects: projectsRes.data.data.total,
          deployments: statsRes.data.data.total,
          success: statsRes.data.data.success,
          failed: statsRes.data.data.failed
        })
      } catch (error) {
        console.error('获取统计数据失败:', error)
      }
    }
    fetchStats()
  }, [])

  return (
    <div>
      <h2>仪表盘</h2>
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="项目数" value={stats.projects} prefix={<ProjectOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="部署总数" value={stats.deployments} prefix={<CloudServerOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="成功部署" value={stats.success} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#3f8600' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="失败部署" value={stats.failed} prefix={<CloseCircleOutlined />} valueStyle={{ color: '#cf1322' }} />
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default Dashboard
