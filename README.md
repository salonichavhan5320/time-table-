# RouteCraft - Advanced Smart Travel Planner

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up the database
Open MySQL and run:
```sql
source database/travel_planner.sql
```

### 3. Configure environment
Edit `.env` file with your credentials:
- MySQL password (already set to `Piyush@1122*`)
- OpenWeather API key (free at openweathermap.org)
- Currency API key (free at exchangerate-api.com)

### 4. Run the app
```bash
python app.py
```
Visit: http://localhost:5000

---

## Project Structure
```
Travel planner/
├── app.py                  # Main Flask application (all routes)
├── config.py               # Configuration (DB, API keys, etc.)
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (secrets)
├── database/
│   └── travel_planner.sql  # Full normalized MySQL schema
├── templates/
│   ├── base.html           # Sidebar + topbar layout
│   ├── index.html          # Landing page
│   ├── login.html          # Login page
│   ├── register.html       # Registration page
│   ├── dashboard.html      # User dashboard with charts
│   ├── trips.html          # Trip list
│   ├── create_trip.html    # Create new trip
│   ├── trip_detail.html    # Trip detail with tabs
│   ├── edit_trip.html      # Edit trip
│   ├── itinerary.html      # Day-wise itinerary
│   ├── expenses.html       # Expense tracker
│   ├── checklist.html      # Travel checklist
│   ├── destinations.html   # Destination explorer
│   ├── destination_detail.html  # Destination + map + weather
│   ├── favorites.html      # Saved favorites
│   ├── profile.html        # User profile
│   ├── emergency_contacts.html  # Emergency contacts
│   ├── notifications.html  # Notifications
│   ├── admin.html          # Admin panel
│   ├── shared_trip.html    # Public shared itinerary
│   └── errors/             # 403, 404, 500 pages
└── static/
    └── uploads/            # User uploaded images
```

## Features Implemented
- ✅ Auth: Register, Login, Logout (bcrypt hashed passwords)
- ✅ Trips: Create, Edit, Delete, View with status tracking
- ✅ Multi-city trip planning with destination selection
- ✅ Auto-generated day-wise itinerary
- ✅ Budget tracker: total, spent, remaining, per-head
- ✅ Expense tracker by category (food, hotel, transport, etc.)
- ✅ Travel checklist with auto-generation
- ✅ Interactive maps (Leaflet + OpenStreetMap)
- ✅ Weather integration (OpenWeatherMap API)
- ✅ Currency converter (ExchangeRate API)
- ✅ PDF export (ReportLab)
- ✅ Trip sharing via unique link
- ✅ Destination explorer with search & filters
- ✅ Favorites system
- ✅ Reviews & ratings
- ✅ Emergency contacts
- ✅ Notifications
- ✅ User profile with photo upload
- ✅ Admin panel
- ✅ Dark mode toggle
- ✅ Responsive mobile-friendly UI
- ✅ Dashboard with Chart.js analytics
- ✅ Normalized MySQL schema with foreign keys

## API Endpoints
| Endpoint | Description |
|---|---|
| `GET /api/weather/<city>` | Current weather for a city |
| `GET /api/currency?from=INR&to=USD&amount=100` | Currency conversion |
| `GET /api/destinations/search?q=goa` | Search destinations |
| `GET /api/trips/<id>/budget` | Trip budget breakdown |
