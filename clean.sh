#bin/sh

if [[ -a coverage.xml ]];then
   rm coverage.xml
fi;

if [[ -a trpc_task.log ]];then
   rm trpc_task.log
fi;

if [[ -a trpc.log.gz ]];then
   rm trpc.log.gz
fi;

if [ -d "htmlcov" ]
then 
    rm htmlcov/ -r
fi

if [ -d "build" ]
then 
    rm build/ -r
fi

if [ -d "dist" ]
then 
    rm dist/ -r
fi

if [ -d "venv" ]
then 
    rm venv/ -r
fi

rm *.log
rm .__*
rm .coverage
rm *.egg-info/ -r

find -type d | grep __pycache__ | xargs rm -r
