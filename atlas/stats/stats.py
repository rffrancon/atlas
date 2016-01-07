from math import exp 
from math import factorial 
from math import log 

def percent_coverage_from_expected_coverage(coverage):
	## With low coverage we expect a lower percent of the sequence to be coverage. 
	return 1 - exp(-coverage)

def log_poisson_prob(lam, k):
	return -lam  + k*log(lam) - log_factorial(k); 

def log_factorial(n):
	assert n >= 0 
	out = 0
	for i in range(int(n)):
		out += log(i + 1)
	return out

def log_lik_depth(depth, expected_depth):
	if expected_depth <= 0:
		raise ValueError("Expected depth must be greater than 0")
	if depth < 0:
		raise ValueError("Depth must not be negative")
	return log_poisson_prob(lam = expected_depth, k = depth)

def log_lik_R_S_coverage(non_error_depth, error_depth, expected_depth, error_rate):
  lne = log_poisson_prob(lam = expected_depth, k = non_error_depth)
  # S allele 
  le = log_poisson_prob(lam = expected_depth * error_rate, k = error_depth)
  return lne+le;  