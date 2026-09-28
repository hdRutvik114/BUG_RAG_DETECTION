import json
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from xgboost import XGBClassifier
from ast_vectorizer import extract_ast_vector_with_tier

df = pd.read_csv('dataset_enriched.csv').dropna(subset=['bug_type'])

def parse_vec(v_str):
    try:
        val = json.loads(v_str)
        if isinstance(val, list) and len(val) == 120:
            return val
    except:
        pass
    return [0.0] * 120

X_buggy_ast = np.array([parse_vec(v) for v in df['buggy_ast_vector']])
X_fixed_ast = np.array([parse_vec(v) for v in df['fixed_ast_vector']])
X_delta_ast = X_fixed_ast - X_buggy_ast

tfidf = TfidfVectorizer(max_features=300, ngram_range=(1, 2), stop_words='english', sublinear_tf=True)
X_tfidf = tfidf.fit_transform(df['buggy_code'].fillna('')).toarray()

X_full = np.hstack([X_buggy_ast, X_delta_ast, X_tfidf])

label_encoder = LabelEncoder()
y = label_encoder.fit_transform(df['bug_type'])
classes = label_encoder.classes_

rf = RandomForestClassifier(n_estimators=180, max_depth=18, random_state=42, n_jobs=-1, class_weight='balanced')
rf.fit(X_full, y)

xgb = XGBClassifier(n_estimators=150, max_depth=6, learning_rate=0.1, random_state=42, eval_metric='mlogloss')
xgb.fit(X_full, y)

ensemble = VotingClassifier(estimators=[('rf', rf), ('xgb', xgb)], voting='soft')
ensemble.fit(X_full, y)

REAL_WORLD_SNIPPETS = [
    {
        "id": 1,
        "title": "Un-awaited MERN Async Database Query in Express Controller",
        "filename": "checkoutController.js",
        "code": """app.post('/checkout', (req, res) => {
    const user = User.findById(req.body.userId);
    res.json({ success: true, balance: user.balance });
});"""
    },
    {
        "id": 2,
        "title": "React Component Unsafe Nested Object Property Access",
        "filename": "UserProfileAvatar.jsx",
        "code": """function UserAvatar(props) {
    const avatarUrl = props.theme.header.userProfile.avatar.src;
    return <img src={avatarUrl} alt="avatar" />;
}"""
    },
    {
        "id": 3,
        "title": "Express NoSQL Operator Injection Vulnerability",
        "filename": "authRoute.js",
        "code": """app.post('/api/login', async (req, res) => {
    const user = await db.collection('users').findOne({
        username: req.body.username,
        password: req.body.password
    });
    res.json(user);
});"""
    },
    {
        "id": 4,
        "title": "Pagination Off-by-One Slice Boundary Index Overrun",
        "filename": "paginationUtils.ts",
        "code": """function getPageItems(items, pageIndex, pageSize) {
    const start = pageIndex * pageSize;
    const end = start + pageSize + 1;
    return items.slice(start, end);
}"""
    },
    {
        "id": 5,
        "title": "Unclosed MongoDB Connection Socket Leak",
        "filename": "reportExporter.js",
        "code": """async function exportReport() {
    const client = await MongoClient.connect(process.env.DB_URI);
    const data = await client.db('analytics').collection('events').find().toArray();
    return data;
}"""
    },
    {
        "id": 6,
        "title": "React Hook Stale Closure inside Interval",
        "filename": "AutoSaverHook.tsx",
        "code": """function AutoSaver({ data }) {
    useEffect(() => {
        const id = setInterval(() => {
            saveToServer(data);
        }, 5000);
        return () => clearInterval(id);
    }, []);
}"""
    }
]

print("==================================================================")
print(" VERIFYING REAL-WORLD ERROR SNIPPETS WITH TRAINED ML PREDICTOR")
print("==================================================================\n")

results = []
for snippet in REAL_WORLD_SNIPPETS:
    ast_vec, tier = extract_ast_vector_with_tier(snippet['code'], snippet['filename'])
    delta_ast = np.zeros(120)
    tfidf_vec = tfidf.transform([snippet['code']]).toarray()[0]
    feat_vec = np.hstack([ast_vec, delta_ast, tfidf_vec]).reshape(1, -1)
    
    probs = ensemble.predict_proba(feat_vec)[0]
    top3_idx = np.argsort(probs)[::-1][:3]
    
    top1_class = classes[top3_idx[0]]
    top1_conf = probs[top3_idx[0]] * 100
    
    top3_list = [(classes[idx], probs[idx] * 100) for idx in top3_idx]
    
    res_entry = {
        'id': snippet['id'],
        'title': snippet['title'],
        'filename': snippet['filename'],
        'code': snippet['code'],
        'tier': tier,
        'top1_class': top1_class,
        'top1_conf': top1_conf,
        'top3': top3_list
    }
    results.append(res_entry)
    
    print(f"--- TEST {snippet['id']}: {snippet['title']} ---")
    print(f"File: {snippet['filename']} | AST Tier: {tier}")
    print(f"Top-1 Prediction : {top1_class.upper()} ({top1_conf:.2f}% confidence)")
    print(f"Top-3 Probabilities: {', '.join([f'{c}: {p:.1f}%' for c, p in top3_list])}")
    print("-" * 66 + "\n")

with open('verification_results.json', 'w') as f:
    json.dump(results, f, indent=2)

print("Saved verification_results.json successfully!")
