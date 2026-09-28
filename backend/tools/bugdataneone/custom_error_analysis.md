# Custom Error Test Report

Generated: 2026-07-29 10:17 UTC

## Summary

This report evaluates the current trained classifiers on a set of novel JavaScript/TypeScript error examples that are likely not present in the original dataset.

## Model Metrics

| Model | Accuracy | Precision (macro) | Recall (macro) | F1 (macro) |
|---|---:|---:|---:|---:|
| random_forest | 0.9681 | 0.9945 | 0.9086 | 0.9471 |
| logistic_regression | 0.942 | 0.8983 | 0.9176 | 0.9036 |
| linear_svc | 0.9623 | 0.9632 | 0.9269 | 0.9421 |
| sgd | 0.9551 | 0.9606 | 0.9094 | 0.9317 |
| complement_nb | 0.8812 | 0.8567 | 0.6836 | 0.7538 |

## Test Case Predictions

### missing-null-check

**Description:** Property access after a possible null value without a guard.

**Code:**

```javascript
function getUserEmail(user) {
  return user.profile.email;
}
```

**Predictions:**

| Model | Predicted Label |
|---|---|
| random_forest | validation_guard |
| logistic_regression | validation_guard |
| linear_svc | validation_guard |
| sgd | other |
| complement_nb | type_error |

### async-await-missing

**Description:** A Promise is returned but not awaited, causing downstream logic to run too early.

**Code:**

```javascript
async function saveUser(user) {
  db.save(user);
  return user;
}
```

**Predictions:**

| Model | Predicted Label |
|---|---|
| random_forest | validation_guard |
| logistic_regression | validation_guard |
| linear_svc | validation_guard |
| sgd | other |
| complement_nb | other |

### sql-injection

**Description:** Unescaped user input interpolated directly into a SQL query string.

**Code:**

```javascript
function findUser(username) {
  return db.query(`SELECT * FROM users WHERE name = '${username}'`);
}
```

**Predictions:**

| Model | Predicted Label |
|---|---|
| random_forest | validation_guard |
| logistic_regression | validation_guard |
| linear_svc | validation_guard |
| sgd | other |
| complement_nb | other |

### performance-loop

**Description:** An expensive loop inside another loop that can be replaced with a single pass.

**Code:**

```javascript
function buildIndex(items) {
  const index = {};
  for (const item of items) {
    for (const tag of item.tags) {
      if (!index[tag]) index[tag] = [];
      index[tag].push(item.id);
    }
  }
  return index;
}
```

**Predictions:**

| Model | Predicted Label |
|---|---|
| random_forest | validation_guard |
| logistic_regression | validation_guard |
| linear_svc | validation_guard |
| sgd | other |
| complement_nb | other |

### api-parameter-mismatch

**Description:** Using the wrong field name for an API payload, likely causing a bad request.

**Code:**

```javascript
function createTicket(data) {
  return axios.post('/tickets', {
    subject: data.title,
    messsage: data.message,
  });
}
```

**Predictions:**

| Model | Predicted Label |
|---|---|
| random_forest | validation_guard |
| logistic_regression | validation_guard |
| linear_svc | validation_guard |
| sgd | other |
| complement_nb | other |

### security-escape

**Description:** Potential XSS when inserting unsanitized content into HTML markup.

**Code:**

```javascript
function render(user) {
  return `<div>${user.name}</div>`;
}
```

**Predictions:**

| Model | Predicted Label |
|---|---|
| random_forest | validation_guard |
| logistic_regression | validation_guard |
| linear_svc | validation_guard |
| sgd | other |
| complement_nb | other |

## Analysis

- The current classifiers are trained on `dataset.csv` with the original `bug_type` labels.
- These examples were selected to exercise novel error categories such as security injection, async timing, API payload mismatch, and missing guard checks.
- If many predictions are `other`, that indicates the model sees these snippets as unlike the trained bug types or not confidently belonging to a smaller class.
- For stronger generalization, the dataset should include more explicit examples of the kinds of errors being tested here.