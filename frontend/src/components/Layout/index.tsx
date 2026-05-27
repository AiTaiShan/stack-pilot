import React from 'react'
import { Layout as AntLayout, Menu } from 'antd'
import { DashboardOutlined, ProjectOutlined, CloudServerOutlined, LogoutOutlined } from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'

const { Header, Sider, Content } = AntLayout

const Layout: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()

  const clearAuth = useAuthStore((state) => state.clearAuth)

  const handleLogout = () => {
    clearAuth()
    navigate('/login')
  }

  const menuItems = [
    { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
    { key: '/projects', icon: <ProjectOutlined />, label: '项目管理' },
    { key: '/deployments', icon: <CloudServerOutlined />, label: '部署记录' },
    { key: '/logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
  ]

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider>
        <div style={{ height: 32, margin: 16, color: 'white', fontSize: 18, fontWeight: 'bold', textAlign: 'center' }}>
          StackPilot
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => {
            if (key !== '/logout') navigate(key)
          }}
        />
      </Sider>
      <AntLayout>
        <Header style={{ background: '#fff', padding: '0 24px' }} />
        <Content style={{ margin: '24px 16px', padding: 24, background: '#fff' }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  )
}

export default Layout
