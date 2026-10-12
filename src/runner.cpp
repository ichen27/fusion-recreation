#include "cad/commands.hpp"
#include "cad/exchange.hpp"
#include "protocol.hpp"
#include <iostream>
#include <poll.h>
#include <sys/wait.h>
#include <unistd.h>
#include <csignal>
#include <cerrno>
using namespace cad;
namespace {
void emit(Json reply){reply["protocolVersion"]=1;std::cout<<reply.dump()<<std::endl;}
struct Worker {
 pid_t pid=-1;int fd=-1;Id job;bool preview=false;std::string output;
 void finish(bool killChild){
  if(pid>0){if(killChild)kill(pid,SIGKILL);int status;while(waitpid(pid,&status,0)<0&&errno==EINTR){}}
  if(fd>=0)close(fd);pid=-1;fd=-1;output.clear();
 }
 ~Worker(){finish(preview);}
};
Json view(const Snapshot& s){
 Json bodies=Json::array();
 for(auto& f:s.document.features)if(f.kind!=FeatureKind::Sketch&&isValid(f.shape))
  bodies.push_back({{"featureId",f.id},{"volume",volume(f.shape)},{"bounds",bounds(f.shape)}});
 return {{"ok",true},{"kind","snapshot"},{"documentId",s.document.id},{"revision",s.document.revision},{"document",encode(s.document)},{"bodies",bodies}};
}
}
int main(int argc,char** argv){
 signal(SIGPIPE,SIG_IGN);
 try{
  std::filesystem::path path;Id document="document";bool allowFaults=false;
  for(int i=1;i<argc;++i){
   std::string arg=argv[i];
   if(arg=="--store"&&i+1<argc)path=argv[++i];
   else if(arg=="--document"&&i+1<argc)document=argv[++i];
   else if(arg=="--allow-test-faults")allowFaults=true;
   else throw std::runtime_error("Usage: cad-runner --store PATH [--document ID] [--allow-test-faults]");
  }
  if(path.empty())throw std::runtime_error("--store is required");
  CommandStore store(path,document);Worker worker;std::string input;bool running=true;
  auto handle=[&](const std::string& line){
   try{
    auto j=Json::parse(line);
    if(!j.at("protocolVersion").is_number_integer()||j.at("protocolVersion")!=1){emit(errorReply(fail("UnsupportedProtocol","Only protocolVersion 1 is supported")));return;}
    auto kind=j.at("kind").get<std::string>();
    if(kind=="shutdown"){running=false;emit({{"ok",true},{"kind","shutdown"}});return;}
    if(kind=="snapshot"){auto s=store.snapshot();emit(s?view(s.value()):errorReply(s.error()));return;}
    if(kind=="cancel"){
     auto id=j.at("jobId").get<Id>();
     if(worker.pid<0||worker.job!=id){emit(errorReply(fail("UnknownJob","No matching worker")));return;}
     if(!worker.preview){emit(errorReply(fail("NotCancellable","Committed commands cannot be cancelled; use Undo")));return;}
     worker.finish(true);emit({{"ok",true},{"kind","cancelled"},{"jobId",id}});return;
    }
    if(kind!="commit"&&kind!="preview"&&kind!="exportStep")throw std::runtime_error("Unknown message kind");
    if(worker.pid>0){emit(errorReply(fail("Busy","One worker is already running")));return;}
    bool preview=kind=="preview";
    auto id=preview?j.at("jobId").get<Id>():Id{};
    if(preview&&(id.empty()||id.size()>256))throw std::runtime_error("Invalid jobId");
    bool stop=j.value("testStopWorker",false);
    if(stop&&(!allowFaults||!preview))throw std::runtime_error("Test fault is disabled");
    Command command;
    std::filesystem::path exportPath;
    if(kind=="exportStep")exportPath=j.at("path").get<std::string>();
    else command=decodeCommand(j.at("command"));
    int pipes[2];if(pipe(pipes)<0)throw std::runtime_error("Cannot create worker pipe");
    auto pid=fork();
    if(pid<0){close(pipes[0]);close(pipes[1]);throw std::runtime_error("Cannot start worker");}
    if(pid==0){
     close(pipes[0]);dup2(STDERR_FILENO,STDOUT_FILENO);
     if(stop)raise(SIGSTOP);
     Json reply;
     try{
      if(kind=="commit"){auto r=store.apply(command);reply=r?encode(r.value()):errorReply(r.error());reply["kind"]="commit";}
      else if(kind=="preview"){
       auto s=store.snapshot();
       if(!s)reply=errorReply(s.error());
       else{auto r=evaluate(s.value(),command);reply=r?view(r.value().snapshot):errorReply(r.error());if(r){reply["proposedRevision"]=r.value().snapshot.document.revision;reply["revision"]=s.value().document.revision;}}
       reply["kind"]="previewResult";reply["jobId"]=id;
      }else{
       auto s=store.snapshot();auto r=s?exportStep(s.value().document,exportPath):Result<void>(s.error());
       reply=r?Json{{"ok",true},{"kind","exportStep"},{"path",exportPath.string()}}:errorReply(r.error());
      }
     }catch(const std::exception& e){reply=errorReply(fail("WorkerFailure",e.what()));}
     auto data=reply.dump();size_t sent=0;
     while(sent<data.size()){auto n=write(pipes[1],data.data()+sent,data.size()-sent);if(n<0&&errno==EINTR)continue;if(n<=0)break;sent+=size_t(n);}
     close(pipes[1]);_exit(0);
    }
    close(pipes[1]);worker.pid=pid;worker.fd=pipes[0];worker.job=id;worker.preview=preview;
    if(preview)emit({{"ok",true},{"kind","accepted"},{"jobId",id}});
   }catch(const std::exception& e){emit(errorReply(fail("InvalidMessage",e.what())));}
  };
  while(running){
   auto polledPid=worker.pid;
   pollfd fds[2]={{STDIN_FILENO,POLLIN,0},{worker.fd,POLLIN,0}};
   int r=poll(fds,worker.fd>=0?2:1,-1);if(r<0){if(errno==EINTR)continue;throw std::runtime_error("poll failed");}
   if(fds[0].revents&(POLLIN|POLLHUP)){
    char chunk[8192];auto n=read(STDIN_FILENO,chunk,sizeof(chunk));if(n<=0)break;
    input.append(chunk,size_t(n));
    size_t newline;
    while(running&&(newline=input.find('\n'))!=std::string::npos){auto line=input.substr(0,newline);input.erase(0,newline+1);if(line.size()>4*1024*1024)emit(errorReply(fail("MessageTooLarge","4 MiB message limit")));else handle(line);}
    if(input.size()>4*1024*1024){emit(errorReply(fail("MessageTooLarge","4 MiB message limit")));break;}
   }
   // Input handling can cancel or replace the worker; compare descriptors.
   if(worker.pid==polledPid&&worker.fd>=0&&fds[1].fd==worker.fd&&(fds[1].revents&(POLLIN|POLLHUP))){
    char chunk[8192];auto n=read(worker.fd,chunk,sizeof(chunk));
    if(n>0){worker.output.append(chunk,size_t(n));if(worker.output.size()>64*1024*1024){worker.finish(true);emit(errorReply(fail("WorkerFailure","Worker response limit exceeded")));}}
    else{
     auto output=worker.output;worker.finish(false);
     try{emit(Json::parse(output));}catch(...){emit(errorReply(fail("WorkerFailure","Worker exited without a valid result")));}
    }
   }
  }
  return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}
}
