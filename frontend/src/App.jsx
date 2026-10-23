import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import Alerts from "./pages/Alerts";
import Billing from "./pages/Billing";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Medicines from "./pages/Medicines";
import PurchaseOrders from "./pages/PurchaseOrders";
import Sales from "./pages/Sales";
import Stock from "./pages/Stock";
import Suppliers from "./pages/Suppliers";
import Users from "./pages/Users";

export default function App() {
  const { user, ready, can } = useAuth();
  if (!ready) return null;
  if (!user) return <Login />;
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/billing" element={can("billing") ? <Billing /> : <Navigate to="/" />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/medicines" element={<Medicines />} />
        <Route path="/stock" element={<Stock />} />
        <Route path="/purchase-orders" element={<PurchaseOrders />} />
        <Route path="/suppliers" element={<Suppliers />} />
        <Route path="/sales" element={<Sales />} />
        <Route path="/analytics" element={<Navigate to="/" />} />
        <Route path="/users" element={can("users") ? <Users /> : <Navigate to="/" />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  );
}
