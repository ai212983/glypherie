"""Review every admitted change from whole curved-stroke reconstruction."""
from compare_junction_terminals import run
from curved_stroke_recovery import fit

if __name__=='__main__':
    run(fitter=fit, output='curved-stroke-recovery-v1', label='Whole curved stroke')
