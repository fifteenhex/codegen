#pragma once

#if defined(__SQLITEGEN) || defined(__JSONGEN)
#include "codegen/fakeglib.h"
#else
#include <glib.h>
#endif
