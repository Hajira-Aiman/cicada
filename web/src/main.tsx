import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HqApp } from './apps/hq/App';
import { ShopApp } from './apps/shop/App';
import { ChaosApp } from './apps/chaos/App';
import { PhoneApp } from './apps/phone/App';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 2000,
      retry: 1,
    },
  },
});

function RootRouter() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/shop/*" element={<ShopApp />} />
          <Route path="/chaos/*" element={<ChaosApp />} />
          <Route path="/m/*" element={<PhoneApp />} />
          <Route path="/*" element={<HqApp />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RootRouter />
  </React.StrictMode>
);
