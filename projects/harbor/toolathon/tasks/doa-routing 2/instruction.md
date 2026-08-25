The purchase requisitions from 2026 Cycle 1 still need routing for approval.

Can you work out who should sign off on each one, and leave the routing log wherever the finance team would expect to find it.



proble: read the file and give me count of rows and write it to xyz file.

tool: read file


solve.py (gonna write count of rows custom function) : Not a golden soltuion but a helper for extra functions


{
    read file

    solve
    custom functon
}





====

oraclerunner and solve.sh wont change

folder name of test can be anyhing


I have one project at /Users/utkarshsoni/Documents/Turing/TerminalBenchAutochecks/terminal-bench/projects/harbor/toolathon , this is also a project harbor based. Now we need to create a toml which do extensive Quality check on the task similar to how we do in /Users/utkarshsoni/Documents/Turing/TerminalBenchAutochecks/terminal-bench/projects/harbor/trialforge /Users/utkarshsoni/Documents/Turing/TerminalBenchAutochecks/terminal-bench/projects/harbor/trialforge/rubrics/task-implementation.toml , Now here is quite explanation about the project

1. instruction.md → problem statement This is the problem statement of thet task. we need to propelry make sure that the problem statemnet is correct  and proepr not very easy , it should be like medium to complex

solution folder contains trajectory and helpers
2. solution/manifest.json → the trajectory with a nuance It's the golden trajectory — an ordered list of steps. Each step is one of two kinds:

{"do": "call", "tool": "...", "args": {...}} → invoke an MCP gateway tool
{"do": "solve", "name": "fn"} → run a function from solve.py
we need to make sure are proper tools called as per the problem statement, trajectory is proerp arguments are proper or not   tool list is there terminal-bench/projects/harbor/toolathon/extra_references/tool-list.json , like the trajectr should be proepr as per the task. more like trajcory not there is also a issue and other things realted to golden trajecotry.,

3. solution/solve.py → helper functions These are the custom Python functions that do: solve steps call it define function which are related to the task things that cannot be done by tool call Eso we need to check proerp things are defined or not as per the requirement of task, extra things should not be there those kind of checks  trajctory call proper funciton or not if it calls, are helper alionged with problem or not

4. environment/tasks → task assets , here trainer add all the files that are related to the proiblem statemnet he is working on which is defined in instruction.md, we also need to check are the files alinge with the problem stamtent, extra files should be flagged. file data should be aligned, there names also should be aligned not like random names these kind of checks we need

Dockerfile + runtime/setup.sh build the container, start the MCP gateway, and lay down workspace files  we need to make sure that the docker file is alinged and copy all right things, not random not brokn as per the task requiement and those related checks.

5. tests/  this folder contaisn the verifers for the task, we need to make sure trainer written the proepr tests or not, like folder name inside can be diffrent as per the task, but we need to make sure folder name  align with the checks and problem stamtenet trainer working on, we need to make surre he properly verify the task   less verifer we need to flag, extra verifier check wee need to flag. we also need to make sure the expeected file that trainer added if required by the problem stamtnet is also correct or not, judge it acc to the instrucition. Need detailed checks on the verifer that are those alinged or not.  also not broken or random checks, 

we can also check other stuffs like task toml file  are proper tools defined or not MCP_SERVERS = "filesystem,terminal,excel,word" as per the task tools can be extra but not less  and other checks, Do a detail analysis of the  terminal-bench/projects/harbor/toolathon/tasks/doa-routing 2 task, undertstand each and every aspect of the task and then desing a detailed quality check toml that should properly judge the entier task that is given, .




Do also check terminal-bench/projects/harbor/toolathon/other_team_checks if something useful you find here this is other team checks, it can be wrong as well. above explantion i did was correct but you can check if any good check you find ther to add as refrence. 

Rest do a detail undestand of other proejct toml as well and do a detial understanding of the current task doa rounting 2 , understand each and every aspect of the task and design a detailed task-implementaion toml file that do a detailed quality check of the task.  Above things i defined is just examples, you need to propperly design detailed quality checks same pass fail rubric as we did on other ,  doa-routing 2  is the most udpated task, rest task are outdated they dont have trajecotry so refer doa routing 2 for detail view, I want a detailed best qc for the task
