from ast_vectorizer import extract_ast_vector_with_tier, is_reliable_tier
import numpy as np

code = 'async function fetchUser(id) { const user = await db.find(id); return user; }'
vec, tier = extract_ast_vector_with_tier(code, 'test.js')
print(f'Tier: {tier}')
print(f'Vector shape: {vec.shape}, norm: {round(float(np.linalg.norm(vec)), 6)}')
print(f'is_reliable_tier(this tier): {is_reliable_tier(tier)}')
print(f'is_reliable_tier(tier_3_fallback): {is_reliable_tier("tier_3_fallback")}')
print(f'is_reliable_tier(tier_1_direct): {is_reliable_tier("tier_1_direct")}')
assert vec.shape == (64,), f"Expected (64,) got {vec.shape}"
assert not np.all(vec == 0), "Vector is all zeros"
print("ALL TESTS PASSED")
