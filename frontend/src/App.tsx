import React from 'react';
import { ThemeProvider } from './context/ThemeContext';
import { AppProvider, useAppContext } from './context/AppContext';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { Dashboard } from './pages/Dashboard';
import { DocumentGenerator } from './pages/DocumentGenerator';
import { History } from './pages/History';
import { Settings } from './pages/Settings';

function PageRouter() {
  const { activePage } = useAppContext();
  return (
    <main className="flex-1 overflow-y-auto">
      {activePage === 'dashboard' && <Dashboard />}
      {activePage === 'generator' && <DocumentGenerator />}
      {activePage === 'history' && <History />}
      {activePage === 'settings' && <Settings />}
    </main>
  );
}

function AppShell() {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <PageRouter />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AppProvider>
        <AppShell />
      </AppProvider>
    </ThemeProvider>
  );
}
