import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
import joblib
import os

# Load elements.xlsx
elements = pd.read_excel('elements.xlsx')

# Generate synthetic data
np.random.seed(42)
n_samples = 1000
data = {
    'Element': np.random.choice(elements['Element'], n_samples),
    'Quantity': np.random.uniform(1, 100, n_samples),
    'People': np.random.randint(1, 10, n_samples),
    'Cost_per_Unit': np.random.uniform(50, 2000, n_samples),
    'Time_per_Unit_Days': np.random.uniform(0.1, 5, n_samples)
}
df = pd.DataFrame(data)

# Merge with elements to get Unit
df = df.merge(elements[['Element', 'Unit']], on='Element', how='left')

# Save synthetic data
df.to_csv('synthetic_data.csv', index=False)

# Prepare features and targets
X = df[['Quantity', 'People']]
y_time = df['Time_per_Unit_Days']
y_cost = df['Cost_per_Unit']

# Train-test split
X_train, X_test, y_time_train, y_time_test = train_test_split(X, y_time, test_size=0.2, random_state=42)
_, _, y_cost_train, y_cost_test = train_test_split(X, y_cost, test_size=0.2, random_state=42)

# Train models
time_model = RandomForestRegressor(n_estimators=100, random_state=42)
time_model.fit(X_train, y_time_train)
cost_model = RandomForestRegressor(n_estimators=100, random_state=42)
cost_model.fit(X_train, y_cost_train)

# Evaluate
print('Time Model MSE:', mean_squared_error(y_time_test, time_model.predict(X_test)))
print('Cost Model MSE:', mean_squared_error(y_cost_test, cost_model.predict(X_test)))

# Save models
os.makedirs('models', exist_ok=True)
joblib.dump(time_model, 'models/time_model.pkl')
joblib.dump(cost_model, 'models/cost_model.pkl')
print('Models saved to models/time_model.pkl and models/cost_model.pkl')