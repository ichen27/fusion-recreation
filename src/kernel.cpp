#include "cad/kernel.hpp"
#include "native.hpp"
#include <BRepBuilderAPI_MakePolygon.hxx>
#include <BRepBuilderAPI_MakeFace.hxx>
#include <BRepPrimAPI_MakePrism.hxx>
#include <BRepPrimAPI_MakeCylinder.hxx>
#include <BRepAlgoAPI_Cut.hxx>
#include <BRepCheck_Analyzer.hxx>
#include <BRepGProp.hxx>
#include <BRepBndLib.hxx>
#include <Bnd_Box.hxx>
#include <GProp_GProps.hxx>
#include <Standard_Failure.hxx>
#include <gp_Ax2.hxx>
#include <TopoDS_Face.hxx>
#include <TopoDS_Wire.hxx>
#include <gp_Vec.hxx>
#include <cmath>
#include <algorithm>
namespace cad {
namespace {
bool dimension(double x){return std::isfinite(x)&&x>1e-7&&x<=1e6;}
double orient(Point2 a,Point2 b,Point2 c){return (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);}
bool on(Point2 a,Point2 b,Point2 p,double eps){
 return std::abs(orient(a,b,p))<=eps&&p.x>=std::min(a.x,b.x)-eps&&p.x<=std::max(a.x,b.x)+eps&&p.y>=std::min(a.y,b.y)-eps&&p.y<=std::max(a.y,b.y)+eps;
}
bool intersects(Point2 a,Point2 b,Point2 c,Point2 d,double eps){
 auto u=orient(a,b,c),v=orient(a,b,d),w=orient(c,d,a),x=orient(c,d,b);
 return ((u>eps&&v< -eps)||(u< -eps&&v>eps))&&((w>eps&&x< -eps)||(w< -eps&&x>eps)) ||
 on(a,b,c,eps)||on(a,b,d,eps)||on(c,d,a,eps)||on(c,d,b,eps);
}
bool profileValid(const Profile& p){
 auto n=p.vertices.size();if(!p.closed||n<3||n>4096)return false;
 double scale=1,area=0;
 for(auto v:p.vertices){if(!std::isfinite(v.x)||!std::isfinite(v.y)||std::abs(v.x)>1e6||std::abs(v.y)>1e6)return false;scale=std::max({scale,std::abs(v.x),std::abs(v.y)});}
 auto eps=1e-12*scale*scale;
 for(size_t i=0;i<n;i++){
  auto a=p.vertices[i],b=p.vertices[(i+1)%n];
  if(std::hypot(a.x-b.x,a.y-b.y)<=1e-7)return false;
  area+=a.x*b.y-b.x*a.y;
  for(size_t j=i+1;j<n;j++){if(j==(i+1)%n||i==(j+1)%n)continue;
   if(intersects(a,b,p.vertices[j],p.vertices[(j+1)%n],eps))return false;
  }
 }
 return std::abs(area)>eps;
}
}
bool isValid(const Shape& s){try{return !Native::get(s).IsNull()&&BRepCheck_Analyzer(Native::get(s)).IsValid();}catch(...){return false;}}
double volume(const Shape& s){GProp_GProps p;BRepGProp::VolumeProperties(Native::get(s),p);return p.Mass();}
std::array<double,6> bounds(const Shape& s){
 Bnd_Box box;BRepBndLib::AddOptimal(Native::get(s),box,false,false);double a,b,c,d,e,f;box.Get(a,b,c,d,e,f);return {a,b,c,d,e,f};
}
Result<Shape> extrude(const Profile& p,double depth){
 if(!dimension(depth))return fail("InvalidDimension","Depth must be finite and between 1e-7 and 1e6 mm");
 if(!profileValid(p))return fail("InvalidProfile","Require explicitly closed, nondegenerate, simple finite profile");
 try{
  BRepBuilderAPI_MakePolygon wire;for(auto v:p.vertices)wire.Add(gp_Pnt(v.x,v.y,0));wire.Close();
  BRepBuilderAPI_MakeFace face(wire.Wire());if(!face.IsDone())return fail("InvalidProfile","Face construction failed");
  BRepPrimAPI_MakePrism prism(face.Face(),gp_Vec(0,0,depth));
  if(!prism.IsDone())return fail("KernelFailure","Extrusion failed");
  auto shape=Native::wrap(prism.Shape());
  if(!isValid(shape)||volume(shape)<=0)return fail("InvalidShape","Extrusion produced invalid/nonpositive solid");
  return shape;
 }catch(const Standard_Failure& e){return fail("KernelFailure",e.what());}
}
Result<Shape> cutCylinder(const Shape& base,const Circle& circle,double depth){
 if(!dimension(depth)||!dimension(circle.radius)||!std::isfinite(circle.center.x)||!std::isfinite(circle.center.y)||std::abs(circle.center.x)>1e6||std::abs(circle.center.y)>1e6)
  return fail("InvalidDimension","Finite positive hole dimensions required");
 if(!isValid(base))return fail("InvalidShape","Invalid base shape");
 try{
  auto b=bounds(base);
  BRepPrimAPI_MakeCylinder tool(gp_Ax2(gp_Pnt(circle.center.x,circle.center.y,b[2]),gp_Dir(0,0,1)),circle.radius,depth);
  BRepAlgoAPI_Cut cut(Native::get(base),tool.Shape());cut.Build();
  if(!cut.IsDone())return fail("KernelFailure","Cylinder cut failed");
  auto result=Native::wrap(cut.Shape());
  if(!isValid(result)||volume(result)<=0)return fail("InvalidShape","Cut removed or invalidated entire body");
  if(volume(base)-volume(result)<1e-8)return fail("NoIntersection","Hole does not remove material");
  return result;
 }catch(const Standard_Failure& e){return fail("KernelFailure",e.what());}
}
}
