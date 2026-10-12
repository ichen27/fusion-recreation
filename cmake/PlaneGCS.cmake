file(READ "${CMAKE_CURRENT_SOURCE_DIR}/deps/lock.json" CAD_LOCK)
string(JSON FREECAD_DIR GET "${CAD_LOCK}" sources freecad directory)
string(JSON EIGEN_DIR GET "${CAD_LOCK}" sources eigen directory)
string(JSON BOOST_DIR GET "${CAD_LOCK}" sources boost directory)
string(JSON JSON_DIR GET "${CAD_LOCK}" sources json directory)
set(GCS_DIR "${CAD_DEPS}/${FREECAD_DIR}/src/Mod/Sketcher/App/planegcs")
add_library(planegcs SHARED
 "${GCS_DIR}/GCS.cpp" "${GCS_DIR}/Constraints.cpp" "${GCS_DIR}/Geo.cpp"
 "${GCS_DIR}/SubSystem.cpp" "${GCS_DIR}/qp_eq.cpp")
target_include_directories(planegcs PUBLIC "${GCS_DIR}"
 "${CMAKE_CURRENT_SOURCE_DIR}/cmake/planegcs"
 "${CAD_DEPS}/${FREECAD_DIR}/src" "${CAD_DEPS}/${EIGEN_DIR}" "${CAD_DEPS}/${BOOST_DIR}")
target_compile_definitions(planegcs PRIVATE Sketcher_EXPORTS)
