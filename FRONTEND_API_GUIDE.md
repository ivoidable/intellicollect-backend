# AWS Billing Intelligence Backend API - Frontend Integration Guide

## 🚀 Quick Start

### Backend Setup
1. **Start the backend server:**
   ```bash
   cd backend
   python main.py
   ```
   Server runs on: `http://localhost:8001`

2. **Verify it's working:**
   ```bash
   curl http://localhost:8001/health
   # Should return: {"status":"healthy","app":"AWS Billing Intelligence Backend","version":"v1","environment":"development"}
   ```

### Frontend Development
- **Base API URL:** `http://localhost:8001/api/v1`
- **API Documentation:** `http://localhost:8001/api/v1/docs` (Interactive Swagger UI)
- **CORS:** Pre-configured for ports `3000`, `3001`, `5173`, `8080`

---

## 📋 API Overview

### Core Entities
- **Customers** - Customer management and profiles
- **Invoices** - Billing and invoice management
- **Payments** - Payment processing and tracking
- **Analytics** - Dashboard metrics and reporting
- **Communications** - Customer notifications and messages

### Authentication
**⚠️ Currently NO authentication required** - All endpoints are open for development

---

## 🔗 Complete API Endpoints

### 🏥 Health & Info
```http
GET /health
GET /
```

**Example:**
```javascript
const health = await fetch('http://localhost:8001/health');
// Returns: {"status": "healthy", "app": "AWS Billing Intelligence Backend", "version": "v1"}
```

---

## 👥 Customers API

### Get All Customers
```http
GET /api/v1/customers/
```

**Query Parameters:**
- `skip` (int): Number of records to skip (default: 0)
- `limit` (int): Max records to return (default: 20, max: 100)
- `search` (string): Search by name or email

**Response:**
```json
{
  "customers": [
    {
      "id": "CUST-4E9E4288",
      "name": "Test Customer 3",
      "email": "test3@example.com",
      "phone": "+1234567890",
      "address": null,
      "company": "Test Corp",
      "industry": "Technology",
      "status": "active",
      "risk_level": null,
      "created_at": "2025-09-21T06:25:48.764832",
      "updated_at": "2025-09-21T06:25:48.764832",
      "created_date": "2025-09-21",
      "total_invoices": 0,
      "outstanding_amount": 0.0,
      "payment_history": null
    }
  ],
  "total": 5,
  "skip": 0,
  "limit": 20
}
```

### Create Customer
```http
POST /api/v1/customers/
```

**Request Body:**
```json
{
  "name": "John Doe",           // Required
  "email": "john@example.com",  // Required
  "phone": "+1234567890",       // Optional
  "address": "123 Main St",     // Optional
  "company": "Tech Corp",       // Optional
  "industry": "Technology"      // Optional
}
```

### Get Single Customer
```http
GET /api/v1/customers/{customer_id}
```

### Update Customer
```http
PUT /api/v1/customers/{customer_id}
```

### Delete Customer
```http
DELETE /api/v1/customers/{customer_id}
```

**Frontend Example:**
```javascript
// Create customer
const createCustomer = async (customerData) => {
  const response = await fetch('http://localhost:8001/api/v1/customers/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(customerData)
  });
  return response.json();
};

// Get customers with pagination
const getCustomers = async (page = 0, limit = 20, search = '') => {
  const params = new URLSearchParams({
    skip: page * limit,
    limit: limit,
    ...(search && { search })
  });

  const response = await fetch(`http://localhost:8001/api/v1/customers/?${params}`);
  return response.json();
};
```

---

## 📄 Invoices API

### Get All Invoices
```http
GET /api/v1/invoices/
```

**Query Parameters:**
- `customer_id` (string): Filter by customer
- `status` (enum): `draft`, `pending`, `sent`, `paid`, `overdue`, `cancelled`
- `payment_status` (enum): `unpaid`, `partial`, `paid`, `refunded`
- `skip`, `limit`: Pagination

**Response:**
```json
{
  "invoices": [
    {
      "invoice_id": "INV-24494765",
      "customer_id": "CUST-4E9E4288",
      "invoice_date": "2025-09-21",
      "due_date": "2025-10-21",
      "amount": 1000.0,
      "total_amount": 1100.0,
      "currency": "USD",
      "status": "draft",
      "payment_status": "unpaid",
      "risk_level": null,
      "risk_score": null,
      "created_timestamp": "2025-09-21T06:26:50.884045",
      "paid_amount": 0.0,
      "outstanding_amount": 1100.0,
      "reminder_count": 0,
      "last_reminder_date": null,
      "payment_date": null,
      "payment_reference": null
    }
  ],
  "total": 2,
  "skip": 0,
  "limit": 20
}
```

### Create Invoice
```http
POST /api/v1/invoices/
```

**Request Body:**
```json
{
  "customer_id": "CUST-4E9E4288",     // Required
  "invoice_date": "2025-09-21",       // Required (YYYY-MM-DD)
  "due_date": "2025-10-21",           // Required (YYYY-MM-DD)
  "amount": 1000.00,                  // Required
  "total_amount": 1100.00,            // Required
  "currency": "USD",                  // Optional (default: USD)
  "status": "draft",                  // Optional (default: draft)
  "payment_status": "unpaid"          // Optional (default: unpaid)
}
```

### Get/Update/Delete Single Invoice
```http
GET /api/v1/invoices/{invoice_id}
PUT /api/v1/invoices/{invoice_id}
DELETE /api/v1/invoices/{invoice_id}
```

---

## 💳 Payments API

### Create Payment
```http
POST /api/v1/payments/
```

**Request Body:**
```json
{
  "customer_id": "CUST-123",
  "amount": 1000.00,
  "currency": "USD",
  "transaction_date": "2025-09-21",
  "reference_number": "PAY-001",
  "status": "success",
  "transaction_type": "bank_transfer",
  "processing_method": "manual",
  "bank_name": "Bank ABC",
  "payer_name": "John Doe",
  "fees": 5.00
}
```

### Get Invoice Payments
```http
GET /api/v1/payments/invoice/{invoice_id}/payments
```

### Upload Receipt
```http
POST /api/v1/payments/upload-receipt
```

**Form Data:**
- `file`: Receipt image/PDF file
- `invoice_id`: Associated invoice ID
- `transaction_id`: Associated transaction ID (optional)

---

## 📊 Analytics API

### Quick Summary Stats
```http
GET /api/v1/analytics/summary
```

**Response:**
```json
{
  "total_customers": 5,
  "total_invoices": 2,
  "total_payments": 3,
  "total_revenue": 3750.0,
  "pending_invoices": 1,
  "last_updated": "2025-09-21T06:33:18.373895"
}
```

### Dashboard Analytics
```http
GET /api/v1/analytics/dashboard?period_days=30
```

**Response:** Comprehensive metrics including revenue, customer, invoice, and risk metrics.

### Revenue Trend
```http
GET /api/v1/analytics/revenue/trend?period=monthly&months=6
```

### Customer Analytics
```http
GET /api/v1/analytics/customer/{customer_id}/analytics
```

---

## 📨 Communications API

### Send Communication
```http
POST /api/v1/communications/send
```

### Get Communication History
```http
GET /api/v1/communications/customer/{customer_id}/history
```

---

## 🛠 Error Handling

### Standard Error Response Format
```json
{
  "detail": "Error message"
}
```

### Validation Errors
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "name"],
      "msg": "Field required",
      "input": {"email": "test@example.com"}
    }
  ]
}
```

### HTTP Status Codes
- `200` - Success
- `201` - Created
- `204` - No Content (for DELETE)
- `400` - Bad Request (validation errors)
- `404` - Not Found
- `500` - Internal Server Error

### Frontend Error Handling Example
```javascript
const handleApiCall = async (apiCall) => {
  try {
    const response = await apiCall();

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'API Error');
    }

    return await response.json();
  } catch (error) {
    console.error('API Error:', error.message);
    throw error;
  }
};
```

---

## 📱 Frontend Integration Examples

### React Hook for API Calls
```javascript
import { useState, useEffect } from 'react';

const useApi = (url, options = {}) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const response = await fetch(`http://localhost:8001${url}`, {
          headers: { 'Content-Type': 'application/json' },
          ...options
        });

        if (!response.ok) throw new Error('API Error');

        const result = await response.json();
        setData(result);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [url]);

  return { data, loading, error };
};

// Usage
const CustomerList = () => {
  const { data: customers, loading, error } = useApi('/api/v1/customers/');

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      {customers?.customers.map(customer => (
        <div key={customer.id}>{customer.name}</div>
      ))}
    </div>
  );
};
```

### Vue.js Composable
```javascript
import { ref, onMounted } from 'vue';

export const useCustomers = () => {
  const customers = ref([]);
  const loading = ref(false);
  const error = ref(null);

  const fetchCustomers = async () => {
    loading.value = true;
    try {
      const response = await fetch('http://localhost:8001/api/v1/customers/');
      const data = await response.json();
      customers.value = data.customers;
    } catch (err) {
      error.value = err.message;
    } finally {
      loading.value = false;
    }
  };

  const createCustomer = async (customerData) => {
    const response = await fetch('http://localhost:8001/api/v1/customers/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(customerData)
    });

    if (response.ok) {
      await fetchCustomers(); // Refresh list
    }
    return response.json();
  };

  onMounted(fetchCustomers);

  return {
    customers,
    loading,
    error,
    fetchCustomers,
    createCustomer
  };
};
```

---

## 🔧 Development Workflow

### 1. Start Backend
```bash
cd backend
python main.py
```

### 2. Verify Connection
```bash
curl http://localhost:8001/health
```

### 3. Explore API
- Visit: `http://localhost:8001/api/v1/docs`
- Interactive API documentation with "Try it out" features

### 4. Test Endpoints
```javascript
// Quick test in browser console
fetch('http://localhost:8001/api/v1/analytics/summary')
  .then(r => r.json())
  .then(console.log);
```

---

## 📋 Data Models Summary

### Customer
```typescript
interface Customer {
  id: string;
  name: string;
  email: string;
  phone?: string;
  address?: string;
  company?: string;
  industry?: string;
  status: 'active' | 'inactive' | 'pending' | 'suspended';
  risk_level?: 'low' | 'medium' | 'high' | 'critical';
  created_at: string;
  updated_at: string;
  created_date?: string;
  total_invoices: number;
  outstanding_amount: number;
  payment_history?: string;
}
```

### Invoice
```typescript
interface Invoice {
  invoice_id: string;
  customer_id: string;
  invoice_date: string; // YYYY-MM-DD
  due_date: string;     // YYYY-MM-DD
  amount: number;
  total_amount: number;
  currency: string;
  status: 'draft' | 'pending' | 'sent' | 'paid' | 'overdue' | 'cancelled';
  payment_status: 'unpaid' | 'partial' | 'paid' | 'refunded';
  risk_level?: string;
  risk_score?: number;
  created_timestamp?: string;
  paid_amount: number;
  outstanding_amount: number;
  reminder_count?: number;
  last_reminder_date?: string;
  payment_date?: string;
  payment_reference?: string;
}
```

---

## 🚨 Important Notes

1. **No Authentication**: Currently no auth system - all endpoints are open
2. **CORS**: Pre-configured for common frontend development ports
3. **Rate Limiting**: Currently disabled for development
4. **Error Handling**: All endpoints return consistent JSON error responses
5. **Validation**: Automatic validation with detailed error messages
6. **Documentation**: Live API docs at `/api/v1/docs`

---

## 🐛 Troubleshooting

### Backend Won't Start
- Check if port 8001 is available
- Verify AWS credentials in `.env`
- Check DynamoDB table access

### CORS Issues
- Ensure your frontend port is in the CORS origins list
- Add your port to `CORS_ORIGINS` in config

### API Errors
- Check the `/api/v1/docs` for exact request formats
- Verify request body structure matches schemas
- Check network tab for detailed error responses

---

## 📞 Quick Reference

- **Base URL**: `http://localhost:8001/api/v1`
- **Health Check**: `http://localhost:8001/health`
- **API Docs**: `http://localhost:8001/api/v1/docs`
- **Server Port**: `8001`
- **Default Frontend Ports**: `3000`, `3001`, `5173`, `8080`

Happy coding! 🚀