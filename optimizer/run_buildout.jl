# Driver for the buildout-time REopt fork. Usage:
#   julia --project=/opt/julia_src run_buildout.jl <scenario.json> <results.json>
using REopt, JuMP, HiGHS, JSON

fp = ARGS[1]
out = ARGS[2]

function newmodel()
    m = Model(HiGHS.Optimizer)
    set_optimizer_attribute(m, "time_limit", 600.0)
    set_optimizer_attribute(m, "mip_rel_gap", 0.01)
    set_silent(m)
    return m
end

@info "Running buildout-time REopt (BAU + optimal)..."
results = run_reopt([newmodel(), newmodel()], fp)

open(out, "w") do f
    JSON.print(f, results)
end
println("DONE_BUILDOUT")
